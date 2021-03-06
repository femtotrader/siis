# @date 2018-12-28
# @author Frederic SCHERMA
# @license Copyright (c) 2018 Dream Overflow
# Strategy trade base class

from datetime import datetime

from notifier.signal import Signal
from common.utils import timeframe_to_str, timeframe_from_str

from trader.order import Order

import logging
logger = logging.getLogger('siis.strategy')


class StrategyTrade(object):
    """
    Strategy trade base abstract class. A trade is related to entry and and one or many exit order.
    It can be created from an automated or manual signal, and having some initial conditions, timeframe, expiry,
    and they are managed according to the policy of a strategy trade manager, or from some other operations added manually
    for semi-automated trading.

    It can only have on entry order. The exit works on the entried quantity. When the entry order is not fully filled,
    the exit order are later adjusted.

    To have partial TP uses multiples trades with different exit levels. Partial TP must be part of your strategy,
    then for a TP50% use two trade with half of the size, the first having a TP at 50% price.    
    """

    __slots__ = '_trade_type', '_entry_state', '_exit_state', '_timeframe', '_operations', '_user_trade', '_next_operation_id', \
        'id', 'dir', 'op', 'oq', 'tp', 'sl', 'aep', 'axp', 'eot', 'xot', 'e', 'x', 'pl', 'ptp', '_stats'

    VERSION = "1.0.0"

    TRADE_UNDEFINED = -1
    TRADE_BUY_SELL = 0    # spot/asset trade
    TRADE_ASSET = 0
    TRADE_SPOT = 0
    TRADE_MARGIN = 1      # individual margin trade position (potentially compatible with hedging markets)
    TRADE_IND_MARGIN = 2  # indivisible margin trade position (incompatible with hedging markets), currently found on crypto

    STATE_UNDEFINED = -1
    STATE_NEW = 0
    STATE_REJECTED = 1
    STATE_DELETED = 2
    STATE_CANCELED = 3
    STATE_OPENED = 4
    STATE_PARTIALLY_FILLED = 5
    STATE_FILLED = 6

    def __init__(self, trade_type, timeframe):
        self._trade_type = trade_type
        
        self._entry_state = StrategyTrade.STATE_NEW
        self._exit_state = StrategyTrade.STATE_NEW

        self._timeframe = timeframe  # timeframe that have given this trade

        self._operations = []      # list containing the operation to process during the trade for semi-automated trading
        self._user_trade = False   # true if the user is responsible of the TP & SL adjustement else (default) strategy manage it

        self._next_operation_id = 1

        self.id = 0      # unique trade identifier
        self.dir = 0     # direction (1 long, -1 short)

        self.op = 0.0    # ordered price (limit)
        self.oq = 0.0    # ordered quantity

        self.tp = 0.0    # take-profit price
        self.sl = 0.0    # stop-loss price

        self.aep = 0.0   # average entry price
        self.axp = 0.0   # average exit price

        self.eot = 0     # entry order opened timestamp
        self.xot = 0     # exit order opened timestamp

        self.e = 0.0     # current filled entry quantity
        self.x = 0.0     # current filled exit quantity (a correctly closed trade must have x == f with f <= q and q > 0)

        self.pl = 0.0    # once closed profit/loss in percent (valid once partially or fully closed)

        self.ptp = 1.0   # partial take-profit rate (only during trade alive)

        self._stats = {
            'best-price': 0.0,
            'best-timestamp': 0.0,
            'worst-price': 0.0,
            'worst-timestamp': 0.0,
            'entry-maker': False,
            'exit-maker': False,
            'entry-fees': 0.0,
            'exit-fees': 0.0,
            'conditions': {}
        }

    #
    # getters
    #

    @classmethod
    def version(cls):
        return cls.VERSION

    @property
    def trade_type(self):
        return self._trade_type

    @property
    def entry_state(self):
        return self._entry_state

    @property
    def exit_state(self):
        return self._exit_state   

    @property
    def direction(self):
        return self.dir
    
    def close_direction(self):
        return -self.dir

    @property
    def entry_open_time(self):
        return self.eot

    @property
    def exit_open_time(self):
        return self.xot

    @property
    def order_quantity(self):
        return self.oq

    @property
    def quantity(self):
        """Synonym for order_quantity"""
        return self.oq

    @property  
    def order_price(self):
        return self.op

    @property
    def take_profit(self):
        return self.tp
    
    @property
    def stop_loss(self):
        return self.sl

    @property
    def entry_price(self):
        return self.aep

    @property
    def exit_price(self):
        return self.axp

    @property
    def exec_entry_qty(self):
        return self.e
    
    @property
    def exec_exit_qty(self):
        return self.x

    @property
    def profit_loss(self):
        return self.pl

    @property
    def partial_tp(self):
        return self.ptp

    @property
    def timeframe(self):
        return self._timeframe

    def set_user_trade(self, user_trade=True):
        self._user_trade = user_trade

    def is_user_trade(self):
        return self._user_trade

    @partial_tp.setter
    def partial_tp(self, ptp):
        self.ptp = ptp

    #
    # processing
    #

    def open(self, trader, market_id, direction, order_type, order_price, quantity, take_profit, stop_loss, leverage=1.0, hedging=None):
        """
        Order to open a position or to buy an asset.

        @param trader Trader Valid trader handler.
        @param market_id str Valid market identifier.
        @param direction int Order direction (1 or -1)
        @param order_type int Order type (market, limit...)
        @param order_price float Limit order price or None for market
        @param quantity float Quantity in unit of quantity
        @param take_profit float Initial take-profit price or None
        @param stop_loss float Initial stop-loss price or None
        @param leverage float For some brokers leverage multiplier else unused
        @param hedging boolean On margin market if True could open positions of opposites directions
        """
        return False

    def remove(self, trader):
        """
        Remove the trade and related remaining orders.
        """
        pass

    def can_delete(self):
        """
        Because of the slippage once a trade is closed deletion can only be done once all the quantity of the
        asset or the position are executed.

        @todo Cleanup the live of a trade.
        """
        if self._entry_state == StrategyTrade.STATE_FILLED and self._exit_state == StrategyTrade.STATE_FILLED:
            # entry and exit are fully filled
            return True

        if self.e >= self.oq and (self.x >= self.e or self.x >= self.oq):
            # in case of state not defined by qty are done : entry fully filled and exit filled whats filled in entry
            # but some cases filled entry is a bit more than orderer (binance...), but need to compare with initial quantity
            return True

        if self.e > 0 and self.x < self.e:
            # entry quantity but exit quantity not fully filled
            return False

        if self._entry_state == StrategyTrade.STATE_NEW or self._entry_state == StrategyTrade.STATE_OPENED:
            # buy order not opened or opened but trade still valid till expiry or cancelation
            return False

        if self.e > 0 and (self._exit_state == StrategyTrade.STATE_NEW or self._exit_state == StrategyTrade.STATE_OPENED):
            # have quantity but sell order not filled
            return False

        return True

    def is_active(self):
        """
        Return true if the trade is active (non-null entry qty, and exit quantity non fully completed).
        """
        if self._exit_state == StrategyTrade.STATE_FILLED:
            return False

        if self.e > 0 and self.x < self.e:
            return True

    def is_opened(self):
        """
        Return true if the entry trade is opened but no qty filled at this moment time.
        """
        return self._entry_state == StrategyTrade.STATE_OPENED

    def is_canceled(self):
        """
        Return true if the trade is not active, canceled or rejected.
        """
        if self._entry_state == StrategyTrade.STATE_REJECTED:
            return True

        if self._entry_state == StrategyTrade.STATE_CANCELED and self.e <= 0:
            return True

        if self._exit_state == StrategyTrade.STATE_CANCELED and self.x <= 0:
            return True

        return False

    def is_opening(self):
        """
        Is entry order in progress.
        """
        return self._entry_state == StrategyTrade.STATE_OPENED or self._entry_state == StrategyTrade.STATE_PARTIALLY_FILLED

    def is_closing(self):
        """
        Is close order in progress.
        """
        return self._exit_state == StrategyTrade.STATE_OPENED or self._exit_state == StrategyTrade.STATE_PARTIALLY_FILLED

    def is_closed(self):
        """
        Is trade fully closed (all qty sold).
        """
        return self._exit_state == StrategyTrade.STATE_FILLED and self.x >= self.e

    def is_entry_timeout(self, timestamp, timeout):
        """
        Return true if the trade timeout.

        @note created timestamp t must be valid else it will timeout every time.
        """
        return (self._entry_state == StrategyTrade.STATE_OPENED) and (self.e == 0) and (self.eot > 0) and ((timestamp - self.eot) >= timeout)

    def is_valid(self, timestamp, validity):
        """
        Return true if the trade is not expired (signal still acceptable) and entry quantity not fully filled.
        """
        return ((self._entry_state == StrategyTrade.STATE_OPENED or self._entry_state == StrategyTrade.STATE_PARTIALLY_FILLED) and
                (self.e < self.oq) and ((timestamp - self.entry_open_time) <= validity))

    def cancel_open(self, trader):
        """
        Cancel the entiere or remaining open order.
        """
        return False

    def cancel_close(self, trader):
        """
        Cancel the entiere or remaining close order.
        """
        return False

    def modify_take_profit(self, trader, market_id, price):
        """
        Create/modify the take-order limit order or position limit.
        """
        return False

    def modify_stop_loss(self, trader, market_id, price):
        """
        Create/modify the stop-loss taker order or position limit.
        """
        return False

    def close(self, trader, market_id):
        """
        Close the position or sell the asset.
        """
        return False

    def order_signal(self, signal_type, data, ref_order_id, instrument):
        pass

    def position_signal(self, signal_type, data, ref_order_id, instrument):
        pass

    def is_target_order(self, order_id, ref_order_id):
        return False

    def is_target_position(self, position_id, ref_order_id):
        return False

    #
    # Helpers
    #

    def direction_to_str(self):
        if self.dir > 0:
            return 'long'
        elif self.dir < 0:
            return 'short'
        else:
            return ''

    def direction_from_str(self, direction):
        if direction == 'long':
            self.dir = 1
        elif direction == 'short':
            self.dir = -1
        else:
            self.dir = 0

    def state_to_str(self):
        """
        Get a string for the state of the trade (only for display usage).
        """
        if self._entry_state == StrategyTrade.STATE_NEW:
            # entry is new, not ordered
            return 'new'
        elif self._entry_state == StrategyTrade.STATE_OPENED:
            # the entry order is created, waiting for filling
            return 'opened'
        elif self._entry_state == StrategyTrade.STATE_REJECTED:
            # the entry order is rejected, trade must be deleted
            return 'rejected'
        elif self._exit_state == StrategyTrade.STATE_REJECTED and self.e > self.x:
            # an exit order is rejectect but the exit quantity is not fully filled (x < e), this case must be managed
            return 'problem'
        elif self.e < self.oq and (self._entry_state == StrategyTrade.STATE_PARTIALLY_FILLED or self._entry_state == StrategyTrade.STATE_OPENED):
            # entry order filling until be fully filled or closed (cancel the rest of the entry order, exiting)
            return 'filling'
        elif self.e > 0 and self.x < self.e and (self._exit_state == StrategyTrade.STATE_PARTIALLY_FILLED or self._exit_state == StrategyTrade.STATE_OPENED):
            # exit order (close order, take-profit order, stop-loss order) are filling (or position take-profit or position stop-loss)
            return 'closing'
        elif (self.e > 0 and self.x >= self.e) or (self._entry_state == StrategyTrade.STATE_FILLED and self._exit_state == StrategyTrade.STATE_FILLED):
            # exit quantity reached the entry quantity the trade is closed, or entry and exit state are set to filled
            return 'closed'
        elif self.e >= self.oq:
            # entry quantity reach ordered quantity the entry is filled
            return 'filled'
        elif self._entry_state == StrategyTrade.STATE_CANCELED and self.e <= 0: 
            return 'canceled'
        else:
            # any others case meaning pending state
            return 'waiting'

    def timeframe_to_str(self):
        return timeframe_to_str(self._timeframe)

    def trade_type_to_str(self):
        if self._trade_type == StrategyTrade.TRADE_ASSET:
            return 'asset'
        elif self._trade_type == StrategyTrade.TRADE_MARGIN:
            return 'margin'
        elif self._trade_type == StrategyTrade.TRADE_MARGIN:
            return 'indisible-margin'
        else:
            return "undefined"

    @staticmethod
    def trade_type_from_str(self, trade_type):
        if trade_type == 'asset':
            return StrategyTrade.TRADE_ASSET
        elif trade_type == 'margin':
            return StrategyTrade.TRADE_MARGIN
        elif trade_type == 'ind-margin':
            return StrategyTrade.TRADE_IND_MARGIN
        else:
            return StrategyTrade.TRADE_UNDEFINED

    def trade_state_to_str(self, trade_state):
        if trade_state == StrategyTrade.STATE_NEW:
            return 'new'
        elif self._trade_type == StrategyTrade.STATE_REJECTED:
            return 'rejected'
        elif self._trade_type == StrategyTrade.STATE_DELETED:
            return 'deleted'
        elif self._trade_type == StrategyTrade.STATE_CANCELED:
            return 'canceled'
        elif self._trade_type == StrategyTrade.STATE_OPENED:
            return 'opened'
        elif self._trade_type == StrategyTrade.STATE_PARTIALLY_FILLED:
            return 'partially-filled'
        elif self._trade_type == StrategyTrade.STATE_FILLED:
            return 'filled'
        else:
            return "undefined"

    @staticmethod
    def trade_state_from_str(self, trade_state):
        if trade_state == 'new':
            return StrategyTrade.STATE_NEW
        elif self._trade_type == 'rejected':
            return StrategyTrade.STATE_REJECTED
        elif self._trade_type == 'deleted':
            return StrategyTrade.STATE_DELETED
        elif self._trade_type == 'canceled':
            return StrategyTrade.STATE_CANCELED
        elif self._trade_type == 'opened':
            return StrategyTrade.STATE_OPENED
        elif self._trade_type == 'partially-filled':
            return StrategyTrade.STATE_PARTIALLY_FILLED
        elif self._trade_type == 'filled':
            return StrategyTrade.STATE_FILLED
        else:
            return StrategyTrade.STATE_UNDEFINED

    #
    # presistance
    #

    def dump_timestamp(self, timestamp):
        return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%dT%H:%M:%S.%f')

    def load_timestamp(self, datetime_str):
        if datetime_str:
            return datetime.strptime(datetime_str, '%Y-%m-%dT%H:%M:%S.%f').timestamp()
        else:
            return 0

    def dumps(self):
        """
        Override this method to make a dumps for the persistance.
        @return dict with at least as defined in this method.
        """
        return {
            'version': self.version,
            'id': self.id,
            'type': self.trade_type_to_str(),
            'entry-state': self._entry_state,  #  self.trade_state_to_str(self._entry_state),
            'exit-state': self._exit_state,  # self.trade_state_to_str(self._exit_state),
            'timeframe': self._timeframe,  # self.timeframe_to_str(),
            'user-trade': self._user_trade,
            'avg-entry-price': self.aep,
            'avg-exit-price': self.axp,
            'take-profit-price': self.tp,
            'stop-loss-price': self.sl,
            'direction': self.dir, # self.direction_to_str(),
            'entry-open-time': self.eot,  # self.dump_timestamp(self.eot),
            'exit-open-time': self.xot,  # self.dump_timestamp(self.xot),
            'order-qty': self.oq,
            'filled-entry-qty': self.e,
            'filled-exit-qty': self.x,
            'profit-loss-rate': self.pl,
            'statistics': self._stats
        }

    def loads(self, data):
        """
        Override this method to make a loads for the persistance model.
        @return True if success.
        """
        self.id = data.get('id', -1)
        self._trade_type = data.get('type', 0)  # self.trade_type_from_str(data.get('type', ''))
        self._entry_state = data.get('entry-state', 0)  # self.trade_state_from_str(data.get('entry-state', ''))
        self._exit_state = data.get('exit-state', 0)  # self.trade_state_from_str(data.get('exit-state', ''))
        self._timeframe =  data.get('timeframe', 0)  # timeframe_from_str(data.get('timeframe', '4h'))
        self._user_trade = data.get('user-trade')

        self._operations = []
        self._next_operation_id = -1

        self.dir = data.get('direction', 0)  # self.direction_from_str(data.get('direction', ''))
        self.oq = data.get('order-qty', 0.0)

        self.tp = data.get('take-profit-price', None)
        self.sl = data.get('stop-loss-price', None)

        self.aep = data.get('avg-entry-price', 0.0)
        self.axp = data.get('avg-exit-price', 0.0)
       
        self.eot = data.get('entry-open-time', 0)  # self.load_timestamp(data.get('entry-open-datetime'))
        self.xot = data.get('exit-open-time', 0)  # self.load_timestamp(data.get('exit-open-datetime'))

        self.e = data.get('filled-entry-qty', 0.0)
        self.x = data.get('filled-exit-qty', 0.0)

        self.pl = data.get('profit-loss-rate', 0.0)

        self._stats = data.get('statistics', {
            'best-price': 0.0,
            'best-timestamp': 0.0,
            'worst-price': 0.0,
            'worst-timestamp': 0.0,
            'entry-maker': False,
            'exit-maker': False,
            'entry-fees': 0.0,
            'exit-fees': 0.0,
            'conditions': {}
        })

        return True

    #
    # stats
    #

    def update_stats(self, last_price, timestamp):
        if self.is_active():
            if self.dir > 0:
                if last_price > self._stats['best-price']:
                    self._stats['best-price'] = last_price
                    self._stats['best-timestamp'] = timestamp

                if last_price < self._stats['worst-price'] or not self._stats['worst-price']:
                    self._stats['worst-price'] = last_price
                    self._stats['worst-timestamp'] = timestamp                    

            elif self.dir < 0:
                if last_price < self._stats['best-price'] or not self._stats['best-price']:
                    self._stats['best-price'] = last_price
                    self._stats['best-timestamp'] = timestamp

                if last_price > self._stats['worst-price']:
                    self._stats['worst-price'] = last_price
                    self._stats['worst-timestamp'] = timestamp

    def best_price(self):
        return self._stats['best-price']

    def worst_price(self):
        return self._stats['worst-price']

    def best_price_timestamp(self):
        return self._stats['best-timestamp']

    def worst_price_timestamp(self):
        return self._stats['worst-timestamp']

    def get_stats(self):
        return self._stats

    def add_condition(self, name, data):
        self._stats['conditions'][name] = data

    def get_conditions(self):
        return self._stats['conditions']

    #
    # operations
    #

    @property
    def operations(self):
        """
        List all pending/peristants operations
        """
        return self._operations

    def cleanup_operations(self):
        """
        Regenerate the list of operations by removing the finished operations.
        """
        ops = []

        for operation in self._operations:
            if not operation.can_delete():
                ops.append(operation)

        # replace the operations list
        self._operations = ops

    def add_operation(self, trade_operation):
        trade_operation.set_id(self._next_operation_id)
        self._next_operation_id += 1

        self._operations.append(trade_operation)

    def remove_operation(self, trade_operation_id):
        for operation in self._operations:
            if operation.id == trade_operation_id:
                self._operations.remove(operation)
                return True

        return False

    def has_operations(self):
        return len(self._operations) > 0
