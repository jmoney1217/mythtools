#!/usr/bin/env python2.7
# -*- coding: UTF-8 -*-

#
# This scrip is based on the 2015 Michael Stucky version which is based on
# Raymond Wagner's transcode wrapper stub.
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
build_seektable = False

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
    rec = Recorded((chanid, starttime), db=db)

    timestr = time.strftime("%m-%d-%y %H:%M:%S")
    title_san = re.sub("\s", ".", rec.title)
    print title_san
    try:
        os.mkdir(log_dir)
    except OSError, e:
        pass
    log_file = os.path.join(log_dir, "%s_transcode_log_%s.txt" % (title_san, timestr))
    trans_log_file = os.path.join(log_dir, "%s_transcode_log_%s.hb.txt" % (title_san, timestr))
    commflag_log_file = os.path.join(log_dir, "%s_transcode_log_%s.cf.txt" % (title_san, timestr))
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
    outfile = '%s.mp4' % infile.rsplit('.',1)[0]

    print 'jobid[%s] chanid[%s] starttime[%s]' % (jobid, chanid, starttime)
    print "Infile: %s" % infile
    print "Outfile: %s" % outfile

    if os.path.splitext(infile)[1] == '.mp4':
        print 'Infile is already mp4! Dont do anything!'
        sys.exit(0)

    # reformat 'starttime' for use with mythtranscode/ffmpeg/mythcommflag
    starttime = str(rec.starttime.utcisoformat().replace(u':', '').replace(u' ', '').replace(u'T', '').replace('-', ''))

    # Lossless transcode to strip cutlist
    if rec.cutlist == 1:
	print 'Removing cutlist...'
        if jobid:
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
            print 'Removing cutlist failure: Command failed with output:\n%s' % e.stderr
            if jobid:
                job.update({'status':304, 'comment':'Removing Cutlist failed'})
            sys.exit(e.retcode)
	print 'Removing cutlist...done'
    else:
	print 'No cutlist found, skipping'
        tmpfile = infile

    # Transcode to mp4
    if jobid:
        job.update({'status':4, 'comment':'Transcoding to mp4'})

    # By removing the db reference we allow the MythTV database connection to close.
    # Will re-open connection after (potentially) long transcode is complete.
    rec = None
    job = None
    db = None

    task = System(path=transcoder, db=db)
    try:
	print 'Transcoding...'
        output = task('--verbose',
                      '--format mp4',
                      '--encoder x264',
                      '--quality 20.0',
                      '--decomb',
                      '--crop 0:0:0:0',
                      '--x264-preset medium',
                      '--h264-profile high',
                      '--h264-level 4.2',
                      '--audio 1,1',
                      '--aencoder copy:ac3,ffaac',
                      '--ab 192,192',
                      '--mixdown none,dpl2',
                      '--arate Auto,Auto',
                      '--drc 0.0,0.0',
                      '--audio-copy-mask aac,ac3,dtshd,dts,mp3',
                      '--audio-fallback ffac3',
                      '--markers',
                      '--large-file',
                      '--optimize',
                      '--input "%s"' % tmpfile,
                      '--output "%s"' % outfile,
                      '>> "%s" 2>&1' % trans_log_file)
    except MythError, e:
        print 'Error: Command failed with output:\n%s' % e.stderr
        if jobid:
            db = MythDB()
            job = Job(jobid, db=db)
            job.update({'status':304, 'comment':'Transcoding to mp4 failed'})
        sys.exit(e.retcode)
    print 'Transcoding...done'

    # Re-establish our connection to the MythTV database after the
    # (potentially) long transcode above.
    db = MythDB()
    if jobid:
        job = Job(jobid, db=db)
        chanid = job.chanid
        starttime = job.starttime
    rec = Recorded((chanid, starttime), db=db)

    if not os.path.isfile(outfile):
        if jobid:
            job.update({'status':304, 'comment':'Transcoded file not found'})
        print 'Error: Transcoded file (%s) not found!' % outfile
        sys.exit(2)

    print 'Updating recording in MythTV DB, set transcoded'
    if jobid:
        job.update({'status':4, 'comment':'Updating database'})
    rec.basename = os.path.basename(outfile)
    rec.filesize = os.path.getsize(outfile)
    rec.transcoded = 1
    rec.seek.clean()
    rec.update()

    if flush_commskip:
        print 'Flushing commskip list'
        if jobid:
            job.update({'status':4, 'comment':'Flushing commskip'})
        for index,mark in reversed(list(enumerate(rec.markup))):
            if mark.type in (rec.markup.MARK_COMM_START, rec.markup.MARK_COMM_END):
                del rec.markup[index]
        rec.bookmark = 0
        rec.cutlist = 0
        rec.markup.commit()
        rec.update()

    if build_seektable:
        print 'Rebuilding seek table...'
        if jobid:
            job.update({'status':4, 'comment':'Rebuilding seektable'})
        task = System(path='mythcommflag')
        task.command('--chanid %s' % chanid,
                     '--starttime %s' % starttime,
                     '--rebuild',
                     '> "%s"' % commflag_log_file)
	print 'Rebuilding seek table...done'

    print 'Removing original files...'
    if jobid:
            job.update({'status':4, 'comment':'Removing original files'})
    try:
        print 'Deleting %s' % infile
        os.remove(infile)
    except OSError:
        pass
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

    print 'Job Done!'
    if jobid:
        job.update({'status':272, 'comment':'Transcode Completed'})

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
        print 'Script must be provided jobid, or chanid and starttime'
        sys.exit(1)

if __name__ == '__main__':
    main()

