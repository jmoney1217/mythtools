#!/usr/bin/env python2.7

from MythTV import Job, Recorded, System, MythDB, MythBE, MythError, MythLog
import sys, os, errno
import logging, logging.handlers
from optparse import OptionParser

LIBDIR = ['/home/mythtv/recordings/Episodes', '/home/mythtv/recordings/Movies', '/home/mythtv/recordings/Showings']
LOGFILE = '/home/mythtv/mythsyncdeletes.log'
MAXLOGSIZE = 5 * 1024 * 1024
MAXLOGS = 1

class RecordingState:
	Recorded, Recording, BusyJob, Autoexpire = range(4)

class recording:
	def __init__(self, mythrec):
		self.mythrec = mythrec
		self.metadata = mythrec.exportMetadata()
		self.program = mythrec.getProgram()
		self.lib_listing = None
		self.state = RecordingState.Recorded

	def dump(self):
		logging.debug("%s: [%s][link: %s]" % (self.metadata.filename, self.state, self.lib_listing))
		logging.debug(self.metadata)
		logging.debug(self.program)
		if self.lib_listing:
			self.lib_listing.dump()

	def match(self, filename):
		if (os.path.split(self.metadata.filename)[1] == os.path.split(filename)[1]):
			return True
		else:
			return False

class lib_listing:
	def __init__(self, listing):
		self.listing = listing
		self.symlink = os.readlink(listing)

	def dump(self):
		logging.debug("%s: [%s]" % (self.listing, self.symlink))

def main():
	' setup logger, all to stdout and INFO and higher to LOGFILE '
	logging.basicConfig(format='%(message)s',
				level=logging.NOTSET)
	loggingfile = logging.handlers.RotatingFileHandler(LOGFILE, maxBytes=(MAXLOGSIZE), backupCount=MAXLOGS)
	loggingfile.setLevel(logging.INFO)
	formatter = logging.Formatter('%(asctime)s: %(message)s', datefmt='%m-%d %H:%M')
	loggingfile.setFormatter(formatter)
	logging.getLogger('').addHandler(loggingfile)

	' connect to mythtv database '
	db = MythDB()
	be = MythBE(db=db)

	' loop all files in lib_dir that are symlinks and create listing '
	listings = []
	for ld in LIBDIR:
		for dp, dn, files in os.walk(ld):
			for file in files:
				filepath = os.path.join(dp,file)
				if (os.path.islink(filepath)):
					listings.append(lib_listing(filepath))

	' get list of all recordings from MythDB, link with library, figure out their status '
	recordings = []
	activeRecordings = []
	activeJobs = []
	newExpireList = []
	mythrecordings = db.searchRecorded()
	recorderList = be.getRecorderList()
	for mrec in mythrecordings:
		logging.debug(mrec)
		rec = recording(mrec)
		recordings.append(rec)

		' skip items already set to autoexpire '
		if (rec.mythrec.autoexpire == 1):
			logging.debug(" - already set to expire, skip")
			continue

		' loop through the list of library items looking for matching recordings, linking them '
		for l in listings:
			if rec.match(l.symlink):
				if rec.lib_listing != None:
					logging.error("UH OH! Linking with something already linked!")
				else:
					rec.lib_listing = l

		' figure out if the recording is active '
		for recorder in recorderList:
			arec = be.getCurrentRecording(recorder)
			if (arec['title'] is not None) and (arec['chanid'] is not 0) and \
			   (arec == rec.program):
				logging.debug(" - currently recording, skip")
				activeRecordings.append(rec)
				rec.state = RecordingState.Recording
				break
		if (rec.state != RecordingState.Recorded):
			continue

		' figuire if the recording is part of an active job '
		jobs = db.searchJobs() #need to generate jobs on each loop
		for job in jobs:
			if job.status in [Job.ABORTING, Job.ERRORING, Job.PAUSED, Job.PENDING, \
					  Job.QUEUED, Job.RETRY, Job.RUNNING, Job.STARTING, Job.STOPPING]:
				jobrec = Recorded((job.chanid, job.starttime), db=db)
				if rec.mythrec == jobrec:
					logging.debug(" - currently part of a job, skip")
					activeJobs.append(rec)
					rec.state = RecordingState.BusyJob
					break
		if (rec.state != RecordingState.Recorded):
			continue

		' potentially add to auto-expire list, and set orphaned recordings to auto-expire '
		if (rec.lib_listing == None) and (rec.state == RecordingState.Recorded):
			logging.debug(" - no link, auto-expire")
			newExpireList.append(rec)
			# rec.mythrec.delete(force=True, rerecord=False)
			rec.mythrec.autoexpire = 1
			rec.mythrec.update()

	' log summary '
	logging.info("")
	logging.info("** Summary **")
	logging.info(" [MythDB Recordings][%s]" % len(recordings))
	logging.info("  - active recordings: %s" % len(activeRecordings))
	for arec in activeRecordings:
		logging.info("   - %s [%s]" % (arec.program, arec.metadata.filename))
	logging.info("  - in progress jobs: %s" % len(activeJobs))
	for ajobs in activeJobs:
		logging.info("   - %s [%s]" % (ajobs.program, ajobs.metadata.filename))

	logging.info("")
	logging.info(" [Mythical Links][%s]" % len(listings))
	logging.info("  - new auto-expire items: %s" % len(newExpireList))
	for d in newExpireList:
		logging.info( "   - %s" % d.program)

if __name__ == '__main__':
	main()
