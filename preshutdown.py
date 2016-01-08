#!/usr/bin/env python2.7

from MythTV import Job, MythDB
import sys

def main():
   db = MythDB()
   jobs = db.searchJobs()
   activejob = 0
   for job in jobs:
      if job.status in [Job.ABORTING, Job.ERRORING, Job.PAUSED, Job.PENDING, \
                        Job.QUEUED, Job.RETRY, Job.RUNNING, Job.STARTING, Job.STOPPING]:
         activejob = 1
         break

   sys.exit(activejob)

if __name__ == '__main__':
   main()
