#!/usr/bin/env python2.7

from MythTV import Job, Recorded, System, MythDB, findfile, MythError, MythLog, datetime

from optparse import OptionParser
from glob import glob
from shutil import copyfile
from datetime import timedelta
import sys
import os
import errno
import time
import re
import subprocess

log_dir = '/home/mythtv/mythbrake_logs'
transcoder = '/usr/bin/HandBrakeCLI'
flush_commskip = True
build_seektable = True

class tee:
    'redirects a write to multiple objects'
    def __init__(self, *writers):
        self.writers = writers
    def write(self, string):
        string = string.strip()
        if len(string) > 0:
            string = '%s\t%s\n' % (time.strftime('%m-%d %H:%M:%S'), string)
            for writer in self.writers:
                writer.write(string)
                writer.flush()

def runjob(jobid=None, chanid=None, starttime=None):
    db = MythDB()
    if jobid:
        job = Job(jobid, db=db)
        chanid = job.chanid
        starttime = job.starttime
    else:
        starttime = datetime.strptime(str(starttime), "%Y%m%d%H%M%S")+timedelta(hours=-5)
    rec = Recorded((chanid, starttime), db=db)

    timestr = time.strftime("%m-%d-%y %H:%M:%S")
    title_san = re.sub("\s", ".", rec.title)
    print title_san
    try:
        os.mkdir(log_dir)
    except OSError, e:
        pass
    log_file = os.path.join(log_dir, "%s_comm_cut_log_%s.txt" % (title_san, timestr))
    trans_log_file = os.path.join(log_dir, "%s_comm_cut_log_%s.snip.txt" % (title_san, timestr))
    print 'Capturing log in %s...' % log_file
    lfp = open(log_file, 'w')
    sys.stdout = tee(sys.stdout, lfp)
    sys.stderr = tee(sys.stderr, lfp)

    print 'Logging into %s' % log_file

    sg = findfile('/'+rec.basename, rec.storagegroup, db=db)
    if sg is None:
        print 'Local access to recording not found.'
        sys.exit(1)

    infile = os.path.join(sg.dirname, rec.basename)
    tmpfile = '%s.tmp' % infile.rsplit('.',1)[0]
    outfile = '%s.cut.mpg' % infile.rsplit('.',1)[0]

    print "Infile: %s" % infile
    print "Outfile: %s" % outfile

    fps_pattern = re.compile(r'(\d{2}.\d{2}) tbr')
    # When calling avconv, it dumps many messages to stderr, not stdout.
    # This may break someday because of that.
    avconv_fps = subprocess.Popen(['avconv', '-i', infile],
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE).communicate()[1]
    if (fps_pattern.search(str(avconv_fps))):
        framerate = float(fps_pattern.search(str(avconv_fps)).groups()[0])
    else:
        fps_pattern = re.compile(r'(\d{2}) tbr')
        if (fps_pattern.search(str(avconv_fps))):  
            framerate = float(fps_pattern.search(str(avconv_fps)).groups()[0])
        else:
            print "Cannot determine framerate... abort"
            sys.exit(1)

    print "Video frame rate: %s" % str(framerate)

    # reformat 'starttime' for use with mythtranscode/ffmpeg/mythcommflag
    starttime = str(rec.starttime.utcisoformat().replace(u':', '').replace(u' ', '').replace(u'T', '').replace('-', ''))

    # Get skip list
    if jobid:
        job.update({'status':4, 'comment':'Getting skip list'})

    task = System(path='mythutil', db=db)
    try:
        output = task('-q',
                      '--getskiplist',
                      '--chanid %d' % chanid,
                      '--starttime %s' % starttime)
    except MythError, e:
        print 'Command failed with output:\n%s' % e.stderr
        if jobid:
            job.update({'status':304, 'comment':'Getting skip list failed'})
        sys.exit(e.retcode)

    print 'Skip list:'
    print output
    output = output.split(':')[1].strip()
    cuts = [ tuple([int(z) for z in y.split('-')]) for y in output.split(',') ]
    print cuts
    starts_with_commercial = False
    if cuts[0][0] == 0:
        starts_with_commercial = True
        print 'Starts with commercial...'
    snip_start = 0
    snip_end = 0
    segment = 1 
    for index, (start, end) in enumerate(cuts):
        snip_end = start
        if snip_end > snip_start:
            print 'Snipping from %d to %d as segment %d' % (snip_start, snip_end, segment)
            segment += 1
            start_time = float(snip_start) / framerate
            duration = float(snip_end - snip_start) / framerate
            print 'avconv -v 16 -i %s -ss %f -t %f -c copy snippet_%d.mpg' % (infile, start_time, duration, segment)
            '''task = System(path='avconv', db=db)
            try:
                output = task('-v 16',
                              '-i %s' % infile,
                              '-ss %f' % start_time,
                              '-t %f' % duration,
                              '-c copy',
                              'snippet_%d.mpg' % segment,
                              '>> %s' % trans_log_file)
            except MythError, e:
                print 'Command failed with output:\n%s' % e.stderr
                if jobid:
                    job.update({'status':304, 'comment':'Removing Cutlist failed'})
                sys.exit(e.retcode)
 



            avconv_command = ('avconv -v 16 -i ' + source_path + ' -ss ' +
                              str(startpoint) + ' -t ' + str(duration) +
                              ' -c copy output' + str(segments) + '.mpg')'''



        snip_start = end
    print 'Snipping from %d to END as segment %d' % (snip_start, segment)
    start_time = float(snip_start) / framerate
    print 'avconv -v 16 -i %s -ss %f -c copy snippet_%d.mpg' % (infile, start_time, segment)
    '''task = System(path='avconv', db=db)
    try:
        output = task('-v 16',
                      '-i %s' % infile,
                      '-ss %f' % start_time,
                      '-c copy',
                      'snippet_%d.mpg' % segment,
                      '>> %s' % trans_log_file)
    except MythError, e:
        print 'Command failed with output:\n%s' % e.stderr
        if jobid:
            job.update({'status':304, 'comment':'Removing Cutlist failed'})
        sys.exit(e.retcode)'''

    sys.exit(0)
'''
    REMOVED BELOW CODE... OLD STUFF

    cutpoints = []
    pointtypes = []
    for cutpoint in cutlist:
        if 'framenum' in cutpoint:
            line = cutpoint.split()
            logger.info("%s - {%s} -- %s - {%s}",
                        line[0], line[1],
                        line[2], line[3])
            if line[1] is '0' and line[3] is '4':
                starts_with_commercial = True
            cutpoints.append(line[1])
            pointtypes.append(line[3])
    cutlist.close()
    os.system('rm .mythExCommflag.edl')
    logger.debug("Starts with commercial? %s",  str(starts_with_commercial))
    logger.debug("Found %s cut points", str(len(cutpoints)))
    segments = 0
    for cutpoint in cutpoints:
        index = cutpoints.index(cutpoint)
        startpoint = float(cutpoints[index])/framerate
        duration = 0
        if index is 0 and not starts_with_commercial:
            logger.debug("Starting with non-commercial")
            duration = float(cutpoints[0])/framerate
            startpoint = 0
        elif pointtypes[index] is '4':
            logger.debug("Skipping cut point type 4")
            continue
        elif (index+1) < len(cutpoints):
            duration = (float(cutpoints[index+1]) -
                        float(cutpoints[index]))/framerate
        logger.debug("Start point [%s]", str(startpoint))
        logger.debug("Duration of segment %s: %s",
                     str(segments),
                     str(duration))
        if duration is 0:
            avconv_command = ('avconv -v 16 -i ' + source_path + ' -ss ' +
                              str(startpoint) + ' -c copy output' +
                              str(segments) + '.mpg')
        else:
            avconv_command = ('avconv -v 16 -i ' + source_path + ' -ss ' +
                              str(startpoint) + ' -t ' + str(duration) +
                              ' -c copy output' + str(segments) + '.mpg')
        logger.info("Running avconv command line {%s}", avconv_command)
        os.system(avconv_command)
        segments = segments + 1
    current_segment = 0
    concat_command = 'cat'
    while current_segment < segments:
        concat_command += ' output' + str(current_segment) + '.mpg'
        current_segment = current_segment + 1
    concat_command += ' >> tempfile.mpg'
    logger.info("Merging files with command %s", concat_command)
    os.system(concat_command)
    return 'tempfile.mpg'
'''

def main():
    parser = OptionParser(usage="usage: %prog [options] [jobid]")

    parser.add_option('--chanid', action='store', type='int', dest='chanid',
            help='Use chanid for manual operation')
    parser.add_option('--starttime', action='store', type='int', dest='starttime',
            help='Use starttime for manual operation')
    parser.add_option('-v', '--verbose', action='store', type='string', dest='verbose',
            help='Verbosity level')

    opts, args = parser.parse_args()

    if opts.verbose:
        if opts.verbose == 'help':
            print MythLog.helptext
            sys.exit(0)
        MythLog._setlevel(opts.verbose)

    if len(args) == 1:
        runjob(jobid=args[0])
    elif opts.chanid and opts.starttime:
        runjob(chanid=opts.chanid, starttime=opts.starttime)
    else:
        print 'Script must be provided jobid, or chanid and starttime.'
        sys.exit(1)

if __name__ == '__main__':
    main()


