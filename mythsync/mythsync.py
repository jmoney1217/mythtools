#!/usr/bin/env python3
import argparse, configparser, email.mime.text, logging, queue, re, select, smtplib,  subprocess, threading, os, sys
import pyinotify

class Transfer:
  def __init__(self, name, localPath, remotePath):
    self.name = name
    self.localPath = localPath
    self.remotePath = remotePath
    self.onComplete = None
  def __repr__(self):
    return 'Transfer(name={name!r}, localPath={localPath!r}, remotePath={remotePath!r})'.format(
      name=self.name, localPath=self.localPath, remotePath=self.remotePath)
  def onTransferComplete(self):
    if self.onComplete:
      self.onComplete(self)

class Deleter:
  def __init__(self, localPath):
    self.log = logging.getLogger(name=self.__class__.__name__)
    self.localPath = localPath
    self.transfers = set()
    self.lock = threading.Lock()
  def addTransfer(self, transfer):
    if transfer:
      self.transfers.add(transfer)
      transfer.onComplete = self.onTransferComplete
  def onTransferComplete(self, transfer):
    with self.lock:
      self.transfers.remove(transfer)
      if not self.transfers:
        self.log.info('delete:%r', self.localPath)
        os.remove(self.localPath)
      else:
        self.log.info('wait:%d', len(self.transfers))

class CalledProcessError(Exception):
  def __init__(self, cmd, rc, output):
    self.cmd = cmd
    self.rc = rc
    self.output = output

def callProcessWithLogger(popenargs, logger, stdout_log_level=logging.DEBUG, stderr_log_level=logging.ERROR, **kwargs):
    child = subprocess.Popen(popenargs, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)
    log_level = {child.stdout: stdout_log_level, child.stderr: stderr_log_level}
    messages = []
    def check_io():
        ready_to_read = select.select([child.stdout, child.stderr], [], [], 1000)[0]
        for io in ready_to_read:
            line = io.readline().rstrip()
            if line:
                logger.log(log_level[io], line)
                messages.append(str(line))
    # keep checking stdout/stderr until the child exits
    while child.poll() is None:
        check_io()
    # check again to catch anything after the process exits
    check_io()  
    return child.wait(), messages

def callWithLogger(cmd, logger, test=False):
    logger.info('command: %r', cmd)
    if test:
      rc = 0
    else:
      rc, messages = callProcessWithLogger(cmd, logger)
    if rc:
      message = 'exited with error code %d'.format(rc)
      logger.error(message)
      messages.append(message)
      raise CalledProcessError(cmd, rc, messages)
    else:
      logger.info('finished')

class WorkQueue(object):
  def __init__(self, name):
    self.name = name
    self.log = logging.getLogger(name=self.__class__.__name__ + '.' + self.name)
    self.createQueue()
  def createQueue(self):
    self.log.info('Queue Created')
    self.queue = queue.Queue()
    self.thread = threading.Thread(target=self.worker)
    self.thread.daemon = True
    self.thread.start()
  def queueWork(self, work):
    self.log.info('Queue: %r', work)
    self.queue.put(work)
  def worker(self):
    self.log.info('Worker started')
    while True:
      work = self.queue.get()
      self.log.info('Execute: %r', work)
      try:
        self.execute(work)
      except:
        self.log.error('Execute Error', exc_info=True)
      self.queue.task_done()

class TransferQueue(WorkQueue):
  def __init__(self, name, config):
    WorkQueue.__init__(self, name)
    self.parseConfig(config)
    self.log.info('email notification: %r', self.emails)
    if self.test:
      self.log.warning('TEST mode enabled')
  def parseConfig(self, config):
    self.host = config.get('host')
    self.bwlimit = config.get('bwlimit')
    email = config.get('email')
    self.emails = email and email.split() or []
    self.test = config.get('test', '').lower() in ('1', 'true')
  def execute(self, transfer):
    try:
      self.doTransfer(transfer)
      emailSubject = 'MythTV: {file} is ready to watch'.format(file=transfer.name)
      emailBody = 'Successfully transfered {transfer.name} to {queue.host}'.format(transfer=transfer, queue=self)
    except CalledProcessError as e:
      emailSubject = 'MythTV: {file} transfer failed'.format(file=transfer.name)
      emailBody = '''\
Command: {cmd}
Failed with error code {rc}
Output:
{output}'''.format(cmd=e.cmd, rc=e.rc, output='\n'.join(e.output))
    transfer.onTransferComplete()
    if self.emails:
      self.sendEmail(
        fromAddress='mythtv@wildfreddy.fivebytestudios.com',
        toAddresses=self.emails,
        subject=emailSubject,
        body=emailBody)
  def getRsyncOptions(self):
    options = []
    if self.bwlimit:
      options.append('--bwlimit=' + self.bwlimit)
    return options
  def doTransfer(self, transfer):
    remoteDir = os.path.split(transfer.remotePath)[0]
    cmd = ['ssh', self.host, 'mkdir', '-p', repr(remoteDir)]
    mkdirLog = logging.getLogger(name='TransferQueue.' + self.name + '.mkdir')
    callWithLogger(cmd, mkdirLog, test=self.test)

    remotePath = self.host + ':' + repr(transfer.remotePath)
    cmd = ['rsync'] + self.getRsyncOptions() + [transfer.localPath, remotePath]
    rsyncLog = logging.getLogger(name='TransferQueue.' + self.name + '.rsync')
    callWithLogger(cmd, rsyncLog, test=self.test)
  def sendEmail(self, fromAddress, toAddresses, subject, body):
    message = email.mime.text.MIMEText(body)
    message['Subject'] = subject
    message['From'] = fromAddress
    message['To'] = ','.join(toAddresses)

    if self.test:
      self.log.info('email: from:%r to:%r %r', fromAddress, toAddresses, message.as_string())
    else:
      smtp = smtplib.SMTP('localhost')
      smtp.sendmail(fromAddress, toAddresses, message.as_string())
      smtp.quit()    

class Distributor:
  def __init__(self, directory, queue, config):
    self.directory = directory
    self.queue = queue
    self.log = logging.getLogger(name='Distributor.' + self.directory + '.' + self.queue.name)
    self.parseConfig(config)
  def parseConfig(self, config):
    pathFilter = config.get('filter', raw=True)
    self.log.info('pathFilter:%r', pathFilter)
    self.pathFilter = re.compile(pathFilter)
    self.destPath = config.get('destpath')
  def onModified(self, localPath, relativePath):
    if self.pathFilter.match(relativePath):
      transfer = Transfer(relativePath, localPath, os.path.join(self.destPath, relativePath))
      self.queue.queueWork(transfer)
      return transfer
    else:
      self.log.info('ignored: %r', relativePath)

class EventHandler(pyinotify.ProcessEvent):
  MASK = pyinotify.IN_CLOSE_WRITE
  def __init__(self, directory, distributors, config):
    self.directory = directory
    self.distributors = distributors
    self.parseConfig(config)
    self.log = logging.getLogger(name='EventHandler.' + self.directory)
  def parseConfig(self, config):
    self.deleteAfter = config.get('delete', fallback=False)
  def process_IN_CLOSE_WRITE(self, event):
    name = os.path.split(event.pathname)[1]
    if not name.startswith('.'):
      relativePath = os.path.relpath(event.pathname, self.directory)
      self.log.info('Modified: %r %r', self.directory, relativePath)

      if self.deleteAfter:
        deleter = Deleter(event.pathname)
      else:
        deleter = None

      for distributor in self.distributors:
        transfer = distributor.onModified(event.pathname, relativePath)
        if deleter:
          deleter.addTransfer(transfer)

def main():
  parser = argparse.ArgumentParser()
  parser.add_argument('directories', metavar='DIR', nargs='+',
    help='directories to watch')
  parser.add_argument('-c', '--config', metavar='FILE',
    help='path to config file')
  parser.add_argument('-l', '--log', metavar='FILE', default=os.path.join(sys.path[0], 'mythsync.log'),
    help='path to log file')
  parser.add_argument('-d', '--daemon', action='store_true',
    help='daemonize process, running in background')
  args = parser.parse_args()

  logging.basicConfig(level=logging.INFO, filename=args.log,
    format='%(asctime)s %(levelname)s:%(name)s %(message)s')

  log = logging.getLogger('mythsync')
  try:
    process(args)
  except:
    log.exception('fatal error in process()')
    raise

def process(args):
  configParser = configparser.ConfigParser(interpolation=configparser.ExtendedInterpolation())
  configPaths = [os.path.join(sys.path[0], 'mythsync.conf'), os.path.expanduser('~/.mythsync')]
  if args.config:
    configPaths.append(args.config)
  configParser.read(configPaths)
  
  transferQueues = {}
  for section, options in configParser.items():
    if section != 'DEFAULT':
      transferQueues[section] = TransferQueue(section, options)

  wm = pyinotify.WatchManager()
  notifier = pyinotify.Notifier(wm)
  for directory in args.directories:
    dirConfigParser = configparser.ConfigParser(interpolation=configparser.ExtendedInterpolation())
    dirConfigParser.read(os.path.join(directory, '.mythsync'))
    distributors = []
    dirConfig = None
    for section, options in dirConfigParser.items():
      if section == 'DEFAULT':
        dirConfig = options
      else:
        distributors.append(Distributor(directory, transferQueues.get(section), options))
    eventHandler = EventHandler(directory, distributors, dirConfig)
    wm.add_watch(path=directory, mask=EventHandler.MASK, proc_fun=eventHandler, rec=True)
  notifier.loop()

if __name__ == '__main__':
  main()
