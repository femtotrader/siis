# @date 2018-09-02
# @author Frederic SCHERMA
# @license Copyright (c) 2018 Dream Overflow
# Indicator base class

class Indicator(object):
    """
    Base class for an indicator.
    @todo https://www.centralcharts.com/fr/forums/12-analyse-technique/1366-indicateur-chande-kroll-stop
    """

    __slots__ = '_name', '_timeframe', '_last_timestamp'

    TYPE_UNKNOWN = 0
    TYPE_AVERAGE_PRICE = 1
    TYPE_MOMENTUM = 2
    TYPE_VOLATILITY = 4
    TYPE_SUPPORT_RESISTANCE = 8
    TYPE_TREND = 16
    TYPE_VOLUME = 32
    TYPE_MOMENTUM_VOLUME = 2|32
    TYPE_MOMENTUM_SUPPORT_RESISTANCE_TREND = 2|8|16

    CLS_UNDEFINED = 0
    CLS_CUMULATIVE = 1
    CLS_INDEX = 2
    CLS_OSCILLATOR = 3
    CLS_OVERLAY = 4

    @classmethod
    def indicator_type(cls):
        return Indicator.TYPE_UNKNOWN

    @classmethod
    def indicator_class(cls):
        return Indicator.TYPE_UNKNOWN

    def __init__(self, name, timeframe):
        self._name = name
        self._timeframe = timeframe

        self._last_timestamp = 0  # last compute timestamp

    @property
    def name(self):
        return self._name
    
    @property
    def indicator_type(self):
        return self._indicator_type

    @property
    def last_timestamp(self):
        return self._last_timestamp

    @property
    def timeframe(self):
        return self._timeframe

    def compute(self, timestamp):
        return None

    def trace(self):
        """
        Return a tuple or dict of the state of the indicator.
        It is used mainly for profiling of the signals.

        This method must be overrided.
        """
        return tuple()
