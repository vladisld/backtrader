#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-
###############################################################################
#
# Copyright (C) 2015, 2016, 2017 Daniel Rodriguez
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
###############################################################################
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import backtrader.feed as feed
from ..utils import date2num
import datetime as dt

TIMEFRAMES = dict(
    (
        (bt.TimeFrame.Seconds, 's'),
        (bt.TimeFrame.Minutes, 'm'),
        (bt.TimeFrame.Days, 'd'),
        (bt.TimeFrame.Weeks, 'w'),
        (bt.TimeFrame.Months, 'm'),
        (bt.TimeFrame.Years, 'y'),
    )
)


class InfluxDB(feed.DataBase):
    frompackages = (
        ('influxdb', [('InfluxDBClient', 'idbclient')]),
        ('influxdb.exceptions', 'InfluxDBClientError')
    )

    params = (
        ('host', '127.0.0.1'),
        ('port', '8086'),
        ('username', None),
        ('password', None),
        ('database', None),
        ('timeframe', bt.TimeFrame.Days),
        ('startdate', None),
        ('high', 'high_p'),
        ('low', 'low_p'),
        ('open', 'open_p'),
        ('close', 'close_p'),
        ('volume', 'volume'),
        ('ointerest', 'oi'),
    )

    def start(self):
        super(InfluxDB, self).start()
        self.biter = None  # bar iterator will be initialized in _preload only
        self.preloaded = False  # indicates that preload was requested and has been completed

    def _preload(self):
        try:
            self.ndb = idbclient(self.p.host, self.p.port, self.p.username,
                                 self.p.password, self.p.database)
        except InfluxDBClientError as err:
            print('Failed to establish connection to InfluxDB: %s' % err)
            raise

        tf = '{multiple}{timeframe}'.format(
            multiple=(self.p.compression if self.p.compression else 1),
            timeframe=TIMEFRAMES.get(self.p.timeframe, 'd'))

        if self.p.fromdate and self.p.todate:
            tcond = "time >= '{fromdate}' AND time <= '{todate}'".format(fromdate=self.p.fromdate, todate=self.p.todate)
        elif self.p.fromdate:
            tcond = "time >= '{fromdate}'".format(fromdate=self.p.fromdate)
        elif self.p.todate:
            tcond = "time <= '{todate}'".format(todate=self.p.todate)
        else:
            tcond = "time <= now()"

        qstr = 'SELECT FIRST("{open_f}") AS "open", MAX("{high_f}") as "high", MIN("{low_f}") as "low", ' \
               'LAST("{close_f}") AS "close", SUM("{vol_f}") as "volume", SUM("{oi_f}") as "openinterest" ' \
               'FROM "{dataname}" ' \
               'WHERE {tcond} ' \
               'GROUP BY time({timeframe}) fill(none) ' \
               'ORDER BY time ASC'.format(open_f=self.p.open, high_f=self.p.high,
                                          low_f=self.p.low, close_f=self.p.close,
                                          vol_f=self.p.volume, oi_f=self.p.ointerest,
                                          dataname=self.p.dataname, tcond=tcond, timeframe=tf)
        try:
            dbars = list(self.ndb.query(qstr, epoch="s").get_points())
        except InfluxDBClientError as err:
            print('InfluxDB query failed: %s' % err)
            raise

        self.biter = iter(dbars)

    def preload(self):
        if not self.biter:
            self._preload()

        while self.load():
            pass

        self._last()
        self.home()

        self.biter = None
        self.preloaded = True

    def _load(self):
        # _load method will not be called by cerebro if preloading was activated
        # just keep that in mind
        if self.preloaded:
            return False

        if not self.biter:
            self._preload()

        try:
            bar = next(self.biter)
        except StopIteration:
            return False

        self.l.datetime[0] = date2num(dt.datetime.fromtimestamp(bar["time"]))
        vol = bar["volume"]
        oi = bar["openinterest"]

        self.l.open[0] = bar["open"]
        self.l.high[0] = bar["high"]
        self.l.low[0] = bar["low"]
        self.l.close[0] = bar["close"]
        self.l.volume[0] = vol if vol else 0.0
        self.l.openinterest[0] = oi if oi else 0.0
        return True
