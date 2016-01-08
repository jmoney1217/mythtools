#!/bin/bash

# Check to see if anyone is currently logged in or if the machine was recently switched on.
# Echoed text appears in log file. It can be removed and --quiet added to the
# grep command once you are satisfied that mythTV is working properly.
# Exit codes:-
# 2 - Machine recently switched on, don't shut down.
# 1 - A user is logged in, don't shut down.
# 0 - No user logged in, OK to shut down.
function checkLogin() {
	# Customizable variables
	MIN_UPTIME=10   # Minimum up time in minutes
	# End of customizable variables

	UPTIME=`cat /proc/uptime | awk '{print int($1/60)}'`

	if [ "$UPTIME" -lt "$MIN_UPTIME" ]; then
		echo $DATE Machine uptime less than $MIN_UPTIME minutes, don\'t shut down.
		return 2
	fi

	# Some configurations ( at least lxdm + xfce4) do not report GUI-logged-on users
	# with "who" or "users".
	# pgrep tests if processes named xfce* exist

	XFCE_PROCS=`pgrep xfce`

	USERS=`who -q | tail -n 1 | sed 's/[a-z #]*=//'`

	if [ "$USERS" == "0" ] && [ "$XFCE_PROCS" == "" ]; then
		echo $DATE No users are logged in, ok to shut down.
		return 0
	else
		echo $DATE Someone is still logged in, don\'t shut down.
		return 1

	fi
}

# check to see if there are any transcode jobs running
# 1 - A transcode job is running, don't shut down.
# 0 - No transcode jobs running, OK to shut down.
function checkTranscode() {
	a=$(pidof -x mythbrake.sh)
	if [ -n "$a" ]; then
		echo $DATE mythbrake transcode running, don\'t shut down.
		return 1
	fi

	return 0
}

# check to see if mythicalLibrarian is running
# 1 - A librarian is running, don't shut down.
# 0 - No librarian is running, OK to shut down.
function checkLibrarian() {
	a=$(pidof -x mythicalLibrarian)
	if [ -n "$a" ]; then
		echo $DATE mythicalLibrarian is running, don\'t shut down.
		return 1
	fi

	return 0
}

# check if there are any MythTV ative jobs
# 1 - A MythTV job is activily running, don't shut down
# 0 - There are no active jobs, OK to shut down
function checkActiveJobs() {
	python /home/mythtv/bin/preshutdown.py
	ret=$?
	if [ $ret -ne 0 ]; then
		echo $DATE MythTV active job, don\'t shut down.
		return 1
	fi

	return 0
}

# Get a date/time stamp to add to log output
DATE=`date +%F\ %T\.%N`
DATE=${DATE:0:23}

checkTranscode
ret=$?
if [ $ret -ne 0 ]; then
	echo $DATE "** preshutdown blocked, transcode in progress."
	exit $ret
fi
checkLibrarian
ret=$?
if [ $ret -ne 0 ]; then
	echo $DATE "** preshutdown blocked, librarian in progress."
	exit $ret
fi
checkLogin
ret=$?
if [ $ret -ne 0 ]; then
        echo $DATE "** preshutdown blocked, user still logged in."
        exit $ret
fi
checkActiveJobs
ret=$?
if [ $ret -ne 0 ]; then
        echo $DATE "** preshutdown blocked, MythTV active jobs."
        exit $ret
fi

exit 0

