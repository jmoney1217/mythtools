#!/usr/bin/env python2.7
# -*- coding: UTF-8 -*-

# 2015 Michael Stucky
# This script is based on Raymond Wagner's transcode wrapper stub.
# Designed to be a USERJOB of the form </path to script/transcode-h264.py %JOBID%>

from MythTV import Job, Recorded, System, MythDB, findfile, MythError, MythLog, datetime

from optparse import OptionParser
from glob import glob
from shutil import copyfile
import sys
import os
import errno
import time
import re

log_dir = '/home/mythtv/mythbrake_logs'
transcoder = '/usr/bin/HandBrakeCLI'
flush_commskip = True
build_seektable = True
job = None

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

def findrecs(title):
    db = MythDB()
    if title is None:
        print 'title is the only supported query right now...'
        return None
    recs = db.searchRecorded(title=title)
    tobedone = []
    for rec in recs:
        #print 'Checking rec:'
        #print rec
        if rec.basename.endswith('mpg'):
            tobedone.append(rec)
        else:
            print 'Skipping non mpg: %s' % rec.basename
    return tobedone 

def getjob(jobid=None, chanid=None, starttime=None):
    db = MythDB()
    if jobid:
        job = Job(jobid, db=db)
        chanid = job.chanid
        starttime = job.starttime
    return Recorded((chanid, starttime), db=db)

def runjob(rec):
    db = MythDB()
    timestr = time.strftime("%m-%d-%y %H:%M:%S")
    title_san = re.sub("\s", ".", rec.title)
    trans_log_file = os.path.join(log_dir, "%s_transcode_log_%s.hb.txt" % (title_san, timestr))
    commflag_log_file = os.path.join(log_dir, "%s_transcode_log_%s.cf.txt" % (title_san, timestr))
    mythical_log_file = os.path.join(log_dir, "%s_transcode_log_%s.ml.txt" % (title_san, timestr))

    sg = findfile('/'+rec.basename, rec.storagegroup, db=db)
    if sg is None:
        print 'Local access to recording not found.'
        sys.exit(1)

    infile = os.path.join(sg.dirname, rec.basename)
    tmpfile = '%s.tmp' % infile.rsplit('.',1)[0]
    outfile = '%s.mp4' % infile.rsplit('.',1)[0]

    print "Infile: %s" % infile
    print "Outfile: %s" % outfile

    # reformat 'starttime' for use with mythtranscode/ffmpeg/mythcommflag
    starttime = str(rec.starttime.utcisoformat().replace(u':', '').replace(u' ', '').replace(u'T', '').replace('-', ''))
    chanid = rec.chanid

    # Lossless transcode to strip cutlist
    if rec.cutlist == 1 and false:
        if job:
            job.update({'status':4, 'comment':'Removing Cutlist'})

        task = System(path='mythtranscode', db=db)
        try:
            output = task('--chanid "%s"' % chanid,
                          '--starttime "%s"' % starttime,
                          '--mpeg2',
                          '--honorcutlist',
                          '-o "%s"' % tmpfile,
                          '2> /dev/null')
        except MythError, e:
            print 'Command failed with output:\n%s' % e.stderr
            if job:
                job.update({'status':304, 'comment':'Removing Cutlist failed'})
            sys.exit(e.retcode)
    else:
        tmpfile = infile
        # copyfile('%s' % infile, '%s' % tmpfile)

    # Transcode to mp4
    if job:
        job.update({'status':4, 'comment':'Transcoding to mp4'})

    print transcoder
    print '-v'
    print '-q 20.0'
    print '-e x264'
    print '-r 25'
    print '--crop 0:0:0:0'
    print '-d'
    print '-m'
    print '-x b-adapt=2:rc-lookahead=50:ref=3:bframes=3:me=umh:subme=8:trellis=1:merange=20:direct=auto'
    print '-i "%s"' % tmpfile
    print '-o "%s"' % outfile
    print '-4'
    print '--optimize 2 >> "%s"' % trans_log_file

    task = System(path=transcoder, db=db)
    try:
        output = task('-v',
                      '-q 20.0',
                      '-e x264',
                      '-r 25',
                      '--crop 0:0:0:0',
                      '-d',
                      '-m',
                      '-x b-adapt=2:rc-lookahead=50:ref=3:bframes=3:me=umh:subme=8:trellis=1:merange=20:direct=auto',
                      '-i "%s"' % tmpfile,
                      '-o "%s"' % outfile,
                      '-4',
                      '--optimize 2 >> "%s"' % trans_log_file)
    except MythError, e:
        print 'Command failed with output:\n%s' % e.stderr
        if job:
            job.update({'status':304, 'comment':'Transcoding to mp4 failed'})
        sys.exit(e.retcode)

    print 'Done transcoding'
    newsize = os.path.getsize(outfile)
    if newsize < 104857600:
        print 'Seems maybe something failed... New size too small: %s' % newsize
        os.remove(outfile)
        return 2

    rec.basename = os.path.basename(outfile)
    try:
        print 'Deleting %s' % infile
        os.remove(infile)
    except OSError:
        pass
    print '''Cleanup the old *.png files'''
    for filename in glob('%s*.png' % infile):
        print 'Deleting %s' % filename
        os.remove(filename)
    try:
        print 'Deleting %s' % tmpfile
        os.remove(tmpfile)
    except OSError:
        pass
    try:
        print 'Deleting %s.map' % tmpfile
        os.remove('%s.map' % tmpfile)
    except OSError:
        pass
    rec.filesize = os.path.getsize(outfile)
    rec.transcoded = 1
    rec.seek.clean()

    print 'Changed recording basename, set transcoded...'

    if flush_commskip:
        print 'Flushing commskip list...'
        for index,mark in reversed(list(enumerate(rec.markup))):
            if mark.type in (rec.markup.MARK_COMM_START, rec.markup.MARK_COMM_END):
                del rec.markup[index]
        rec.bookmark = 0
        rec.cutlist = 0
        rec.markup.commit()

    print 'Updating recording...'
    rec.update()

    if job:
        job.update({'status':4, 'comment':'Rebuilding seektable'})

    if build_seektable:
        print 'Rebuilding seek table'
        task = System(path='mythcommflag')
        task.command('--chanid %s' % chanid,
                     '--starttime %s' % starttime,
                     '--rebuild',
                     '> "%s"' % commflag_log_file)

    if job:
        job.update({'status':4, 'comment':'Running mythical'})

    task = System(path='mythicalLibrarian', db=db)
    try:
        output = task('%s' % outfile,
                      '>> "%s"' % mythical_log_file)
    except MythError, e:
        print 'Command failed with output:\n%s' % e.stderr
        if job:
            job.update({'status':304, 'comment':'Running mythical failed'})
        sys.exit(e.retcode)

    print 'Job Done!...'
    return 0

def main():
    parser = OptionParser(usage="usage: %prog [options] [jobid]")

    parser.add_option('--jobid', action='store', type='int', dest='jobid')
    parser.add_option('--chanid', action='store', type='int', dest='chanid')
    parser.add_option('--starttime', action='store', type='int', dest='starttime')
    parser.add_option('-v', '--verbose', action='store', type='string', dest='verbose',
            help='Verbosity level')
    parser.add_option('--title', action='store', type='string', dest='title',
            help='Title of Show')
    parser.add_option('--limit', action='store', type='int', dest='limit', default=100,
            help='Limit of how many recordings to do')

    opts, args = parser.parse_args()

    if opts.verbose:
        if opts.verbose == 'help':
            print MythLog.helptext
            sys.exit(0)
        MythLog._setlevel(opts.verbose)

    title = None
    if opts.jobid:
        rec = getjob(jobid=opts.jobid)
        title = rec.title 
    elif opts.chanid and opts.starttime:
        rec = getjob(chanid=opts.chanid, starttime=opts.starttime)
        title = rec.title
    elif opts.title:
        title = opts.title

    if title is None:
        print 'Unable to determine title.'
        sys.exit(1)

    timestr = time.strftime("%m-%d-%y %H:%M:%S")
    title_san = re.sub("\s", ".", title)
    print title_san
    try:
        os.mkdir(log_dir)
    except OSError, e:
        pass
    log_file = os.path.join(log_dir, "%s_batch_transcode_log_%s.txt" % (title_san, timestr))
    print 'Capturing log in %s...' % log_file
    lfp = open(log_file, 'w')
    sys.stdout = tee(sys.stdout, lfp)
    sys.stderr = tee(sys.stderr, lfp)

    print 'Logging into %s' % log_file

    print 'Finding all non transcoded shows for title: %s' % title
 
    recs = findrecs(title)
    for rec in recs:
        if opts.limit == 0:
            print 'limit reached, bailing'
            break
        opts.limit -= 1
        print rec
        print rec.basename
        if runjob(rec) == 2:
            print 'skipping this one...'
            opts.limit += 1

    if job:
        job.update({'status':272, 'comment':'Transcode Completed'})

if __name__ == '__main__':
    main()

