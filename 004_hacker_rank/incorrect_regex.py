import re

def is_valid_regex(pattern) :
    try :
        re.compile(pattern)
        print("True")
    except re.error:
        print("False")

a = int(input())

for _ in range(a):
    is_valid_regex(input())
