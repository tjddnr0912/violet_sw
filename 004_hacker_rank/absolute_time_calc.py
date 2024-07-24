#!/bin/python3

import math
import os
import random
import re
import sys
import datetime
#import timedelta

# Complete the time_delta function below.
def time_delta(t1, t2):
    data_format = "%a %d %b %Y %H:%M:%S %z"
    t1_data = datetime.datetime.strptime(t1, data_format)
    t2_data = datetime.datetime.strptime(t2, data_format)
    time_diff = t1_data - t2_data
    time_delta = time_diff.total_seconds()
    return str(abs(int(time_delta)))


if __name__ == '__main__':
    #fptr = open(os.environ['OUTPUT_PATH'], 'w')

    t = int(input())

    for t_itr in range(t):
        t1 = input()

        t2 = input()

        delta = time_delta(t1, t2)

        print(delta)

        #fptr.write(delta + '\n')

    #fptr.close()
