import re as 正则
import os as 系统

def 正则取值(筛子, 标志=0):
    return 正则.compile(筛子, 标志)

def 拼接目录(基目录, 子目录):
    return 系统.path.join(基目录, 子目录)