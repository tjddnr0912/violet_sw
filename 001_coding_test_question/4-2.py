def analysis_3(n) :
    count = 0
    for i in range(n):
        #print(str(i).find('3'))
        if str(i).find('3') != -1:
            #print(i)
            count += 1

    return count

if __name__ == "__main__":
    data = int(input("Write Hours : "))
    result_min = 0

    num3_in_60 = analysis_3(60)
    result_min = (num3_in_60)*60 + (60 - num3_in_60)*num3_in_60

    num3_in_input = analysis_3(data)

    print("The number of 3 between 00:00:00 ~ %2d:59:59 : " %data, num3_in_input*60*60 + (data + 1 - num3_in_input)*result_min)
