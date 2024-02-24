import string
import os
import re

def make_tmp(file_name) :
    txt = ""
    module_name = ""
    with open (file_name) as file:
        for line in file:
            if line.find("input") != -1 or line.find("output") != -1 or line.find("parameter") != -1 or line.find("module") != -1 :
                multi_bit = line.find("[")
                line = line.strip().replace("wire", " ").replace("reg", " ").replace(",", " ").replace("#", " ").replace("(", " ").replace(")", " ").replace("=", " ").split()
                #line = line.strip().replace("wire", " ").replace("reg", " ").replace(",", " ").replace("#", " ").replace("(", " ").replace(")", " ").replace("=", " ").replace("[", " ").replace("]", " ").replace(":", " ").split()
                print(line)
                print(multi_bit)

            if line[0][0] != "/" :
                if line[0] == "module" :
                    module_name = line[1]

                if line[0] == "parameter" :
                    #txt += "{:<20}".format(module_name)
                    txt += "{:<25}{:<20}\n".format(line[0], line[1])
                elif line[0] == "input" or line[0] == "output":
                    #txt += "{:<20}".format(module_name)
                    txt += "{:<10}".format(line[0])
                    if multi_bit != -1 :
                        txt += "{:<30}".format(line[1])
                        txt += "{:<40}".format(line[2])
                        txt += "{:<40}".format(line[2])
                    else :
                        txt += "{:<30}".format(" ")
                        txt += "{:<40}".format(line[1])
                        txt += "{:<40}".format(line[1])
                    txt += "INTR\n" #INTR INPUT OUTPUT

    temp_name = module_name + "_temp"
    if os.path.exists(temp_name) :
        # TODO
        f = open(temp_name, 'w')
        f.write(txt)
    else :
        # TODO
        f = open(temp_name, 'w')
        f.write(txt)

    f.close()

if __name__ == "__main__" :
    #os.system('rm -rf ./*temp')

    make_tmp("./test.v")



