n = int(input())
for _ in range(n):
    x, y = input().split()
    try :
        print(f"{int(x) // int(y)}")
        #z = int(x) / int(y)
        #print(int(x)/int(y))
    except ZeroDivisionError as e :
        print(f"Error Code: integer division or modulo by zero")
        #print(f"Error Code: {e}")
    except ValueError as e :
        #print(f"Error Code: invalid literal for int() with base 10: {e}")
        print(f"Error Code: {e}")

    try :
        print(f"{int(x) // int(y)}")
    except :
        print(f"Error Code")
