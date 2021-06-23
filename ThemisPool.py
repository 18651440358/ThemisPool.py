# coding=utf-8
"""
@Author  : 周灿
@Summary : 自己封装的基于pymysql的Python连接池
"""

import configparser
import os
import queue
import threading
import pymysql


class Config(object):
    def __init__(self, configFileName='db.cnf'):
        file = os.path.join(os.path.dirname(__file__), configFileName)
        self.config = configparser.ConfigParser()
        self.config.read(file)

    def getSections(self):
        return self.config.sections()

    def getOptions(self, section):
        return self.config.options(section)

    def getContent(self, section):
        result = {}
        for option in self.getOptions(section):
            value = self.config.get(section, option)
            result[option] = int(value) if value.isdigit() else value
        return result


# 获取配置文件参数
class parameter(object):
    def __init__(self, password, database, host="localhost", user="root", initsize=3, maxsize=6):
        self.host = str(host)
        self.user = str(user)
        self.password = str(password)
        self.database = str(database)
        self.maxsize = int(maxsize)
        self.initsize = int(initsize)


class ThemisPool(parameter):
    def __init__(self, fileName='db.cnf', configName='mysql'):
        self.config = Config(fileName).getContent(configName)
        super(ThemisPool, self).__init__(**self.config)
        self.pool = queue.Queue(maxsize=self.maxsize)
        self.currentSize = self.initsize
        self._lock = threading.Lock()
        # 初始化连接池
        for i in range(self.initsize):
            self.pool.put(self.createConn())

    # 生产连接
    def createConn(self):
        return pymysql.connect(host=self.host,
                               user=self.user,
                               password=self.password,
                               database=self.database,
                               charset='utf8').cursor()

    # 获取连接
    def getConn(self):
        try:
            self._lock.acquire()
            # 如果池中连接够直接获取
            if not self.pool.empty():
                self.currentSize -= 1
                return self.pool.get()
            else:
                # 否则重新添加新连接
                if self.currentSize < self.maxsize:
                    self.currentSize += 1
                    return self.createConn()
        finally:
            self._lock.release()

    # 释放连接
    def releaseCon(self, conn=None):
        try:
            self._lock.acquire()
            # 如果池中大于初始值就将多余关闭，否则重新放入池中
            if self.pool.qsize() < self.initsize:
                self.pool.put(conn)
                self.currentSize += 1
            else:
                try:
                    conn.close()
                    self.currentSize -= 1
                except pymysql.ProgrammingError as e:
                    raise e
        finally:
            self._lock.release()

    # 执行语句
    def execute(self, sql):
        themis = None
        try:
            themis = self.getConn()
            if themis is None:
                self._lock.acquire()
                while True:
                    themis = self.getConn()
                    if themis is not None:
                        self._lock.release()
                        break
            themis.execute(sql)
            return themis.fetchall()
        finally:
            self.releaseCon(themis)

    def __del__(self):
        while not self.pool.empty():
            self.pool.get().close()