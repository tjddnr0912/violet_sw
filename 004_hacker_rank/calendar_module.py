import calendar

#print(calendar.TextCalendar(firstweekday=6).formatyear(2015))
#
#print(calendar.TextCalendar(firstweekday=6).formatyear(2024))
#
#print(calendar.Calendar.iterweekdays(0))
#
#print(calendar.TextCalendar(firstweekday=6).formatmonth(2024, 7))
#
##print(calendar.TextCalendar(firstweekday=6).weekday(2024, 7, 24))
#
#print(calendar.weekday(2024,7,24))

day_list = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]
mm, dd, yy = map(int, input().split())
if yy <= 2000 or 3000 <= yy :
    print("yy has constraint between 2000 to 3000")
else :
    dow = calendar.weekday(yy, mm, dd)
    print(day_list[dow])

