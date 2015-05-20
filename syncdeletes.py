#!/usr/bin/env python2.7

from MythTV import Job, Recorded, System, MythDB, MythBE, findfile, MythError, MythLog, datetime
import sys, os, errno, time 
from optparse import OptionParser

myth_dir = '/home/mythtv/recordings'
lib_dir = ['/home/mythtv/recordings/Episodes', '/home/mythtv/recordings/Movies', '/home/mythtv/recordings/Showings']
exts = ['.mpg', '.mp4']
notify_email = 'joseph.swantek@gmail.com'

class recording:
	def __init__(self, mythfile):
		self.file = mythfile
		t = os.path.splitext(os.path.basename(mythfile))
		self.chanid = t[0].split('_')[0]
		# self.starttime = datetime.strptime(t[0].split('_')[1], "%Y%m%d%H%M%S")
		self.starttime = t[0].split('_')[1]
		self.ext = t[1].split('.')[1]
		self.state = None
		self.lib_listing = None

	def dump(self):
		print "%s: [%s, %s, %s][link: %s]" % (self.file, self.ext, self.chanid, self.starttime, self.lib_listing)

	def match(self, other):
		if (self.chanid == other.chanid) and (self.starttime == other.starttime) and (self.ext == other.ext):
			return True
		else:
			return False

	def link(self, lib_listing):
		self.lib_listing = lib_listing


class lib_listing:
	def __init__(self, listing):
		self.listing = listing
		self.recording = recording(os.readlink(listing))

	def dump(self):
		print "%s:" % (self.listing)
		self.recording.dump()

def main():
	recordings = []
	listings = []
	' loop all files in myth_dir that are in ext and create recording '
	for f in os.listdir(myth_dir):
		if (os.path.splitext(f)[1] in exts): 
			recordings.append(recording(f))
	print "Recordings found: %s" % len(recordings)
	for r in recordings:
		r.dump()
	
	' loop all files in lib_dir that are symlinks and create listing '
	for ld in lib_dir:	
		for dp, dn, files in os.walk(ld):
			for file in files:
				filepath = os.path.join(dp,file)
				if (os.path.islink(filepath)):
					listings.append(lib_listing(filepath))
	print "Library Items found: %s" % len(listings)
	# for l in listings:
	#	l.dump()

	' loop through the list of library items looking for matching recordings, linking them '
	for l in listings:
		for r in recordings:
			if r.match(l.recording):
				print "MATCH"
				if r.lib_listing != None:
					print "UH OH! Linking with something already linked!"
				else:
					r.link(l)
				r.dump()
				l.recording.dump()

	' for all recordings that are not already deleted (autoexpire) and are now orphaned, set to delete (autoexpire) '
	' be SURE that we dont screw up files that are being recorded now '
	mydb = MythDB()
	mybe = MythBE(db=mydb)	
	#db = MythDB(args=(('DBHostName','localhost'),
        #          ('DBName','mythconverg'),
        #          ('DBUserName','mythtv'),
        #          ('DBPassword','JL82QPNG')))
	r = recordings[2]
	print "[%s, %s]" % (r.chanid, r.starttime)
	rec = Recorded((r.chanid, r.starttime), db=mydb)
	print rec

	' email new delete (autoxpire) list to me '



if __name__ == '__main__':
	main()
