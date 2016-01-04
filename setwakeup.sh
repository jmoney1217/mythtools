#!/bin/bash
#$1 is the first argument to the script. It is the time in seconds since 1970
#this is defined in mythtv-setup with the time_t argument

echo 0 > /sys/class/rtc/rtc0/wakealarm      #this clears your alarm.
echo $1 > /sys/class/rtc/rtc0/wakealarm     #this writes your alarm

LOG_FILE='/var/log/mythtv/hwclock-rebootTime.log' #log file

# Now write the time the system is expected to come out of power save mode
# so there is at least a small record of when if it was supposed to recover

# Note:- Log file will just keep growing

# date in Epoch format
a="`date  +%s`"

# Subtract Current time from Future time
let "b=$1-$a"

# echo $b
# echo "result of time subtraction `date -d @$b`"

# Get Date and Subtract 1,.. as date starts from 1st Jan 1970
dte=`date -d @$b +%d`
let "dte -= 1"

echo "Current Time      ->`date`" >> $LOG_FILE

# Simple check to determine if to include days in output string
if (dte=0)
then
    echo "Shutting down for ->`date -d @$b +%Hhrs:%MMins`" >> $LOG_FILE
else
    echo "Shutting down for ->$[dte]Days `date -d @$b +%Hhrs:%MMins`" >> $LOG_FILE
fi

echo "Wake up at approx.->`date -d @$1`"  >> $LOG_FILE
echo "------------------------------------------------------" >> $LOG_FILE
