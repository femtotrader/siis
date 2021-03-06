# @date 2018-12-28
# @author Frederic SCHERMA
# @license Copyright (c) 2018 Dream Overflow
# Strategy indivisible trade for margin.

from notifier.signal import Signal
from database.database import Database

from trader.order import Order
from .strategytrade import StrategyTrade

import logging
logger = logging.getLogger('siis.strategy')


class StrategyIndMarginTrade(StrategyTrade):
    """
    Specialization for indivisible margin position trade.

    In this case we only have a single position per market without integrated stop/limit.

    We cannot deal in opposite direction at the same time (no hedging),
    but we can evantually manage many trade on the same direction.

    We prefers here to update on trade order signal. A position deleted mean any related trade closed.

    @todo do we need like with asset trade an exit_trades list to compute the axp and x values, because
        if we use cumulative-filled and avg-price we have the same probleme here too.
    """

    __slots__ = 'create_ref_oid', 'stop_ref_oid', 'limit_ref_oid', 'create_oid', 'stop_oid', 'limit_oid', 'position_id', 'stop_order_qty', 'limit_order_qty'

    def __init__(self, timeframe):
        super().__init__(StrategyTrade.TRADE_IND_MARGIN, timeframe)

        self.create_ref_oid = None
        self.stop_ref_oid = None
        self.limit_ref_oid = None

        self.create_oid = None  # related entry order id
        self.stop_oid = None    # related stop order id
        self.limit_oid = None   # related limit order id

        self.position_id = None  # related position id

        self.stop_order_qty = 0.0    # if stop_oid then this is the qty placed on the stop order
        self.limit_order_qty = 0.0   # if limit_oid then this is the qty placed on the limit order

    def open(self, trader, market_id, direction, order_type, order_price, quantity, take_profit, stop_loss, leverage=1.0, hedging=None):
        """
        Open a position or buy an asset.
        """
        order = Order(trader, market_id)
        order.direction = direction
        order.order_price = order_price
        order.order_type = order_type
        order.quantity = quantity
        order.leverage = leverage

        # generated a reference order id
        trader.set_ref_order_id(order)
        self.create_ref_oid = order.ref_order_id

        self.dir = order.direction

        self.op = order.order_price  # retains the order price
        self.oq = order.quantity     # ordered quantity

        self.tp = take_profit
        self.sl = stop_loss

        self._stats['entry-maker'] = not order.is_market()

        if trader.create_order(order):
            self.position_id = order.position_id  # might be market-id

            if not self.eot and order.created_time:
                self.eot = order.created_time

            return True
        else:
            self.create_ref_oid = None

        return False

    def remove(self, trader):
        """
        Remove the order, but doesn't close the position.
        """
        if self.create_oid:
            # cancel the remaining buy order
            if trader.cancel_order(self.create_oid):
                self.create_ref_oid = None
                self.create_oid = None

                self._entry_state = StrategyTrade.STATE_CANCELED

        if self.stop_oid:
            # cancel the stop order
            if trader.cancel_order(self.stop_oid):
                self.stop_ref_oid = None
                self.stop_oid = None
                self.stop_order_qty = 0.0

        if self.limit_oid:
            # cancel the limit order
            if trader.cancel_order(self.limit_oid):
                self.limit_ref_oid = None
                self.limit_oid = None
                self.limit_order_qty = 0.0

    def cancel_open(self, trader):
        if self.create_oid:
            # cancel the buy order
            if trader.cancel_order(self.create_oid):
                self.create_ref_oid = None
                self.create_oid = None

                self._entry_state = StrategyTrade.STATE_CANCELED
            else:
                return False

        return True

    def modify_take_profit(self, trader, market_id, price):
        if self.limit_oid:
            # cancel the limit order and create a new one
            if trader.cancel_order(self.limit_oid):
                self.limit_ref_oid = None
                self.limit_oid = None
                self.limit_order_qty = 0.0
            else:
                return False

        if self.e == self.x:
            # all entry qty is filled
            return True

        if self.e < self.x:
            # something wrong but its ok
            return False

        if self.e > 0:
            # only if filled entry partially or totally
            order = Order(self, market_id)
            order.direction = self.direction
            order.order_type = Order.ORDER_TAKE_PROFIT_LIMIT
            # order.reduce_only = True (not for now because it implies to have the filled qty, and so need to update each time trade qty is updated)
            order.quantity = self.e - self.x  # remaining
            order.order_price = price

            trader.set_ref_order_id(order)
            self.limit_ref_oid = order.ref_order_id

            self._stats['exit-maker'] = not order.is_market()

            if trader.create_order(order):
                self.limit_oid = order.order_id
                self.limit_order_qty = order.quantity

                self.tp = price

                return True
            else:
                self.limit_ref_oid = None
                self.limit_order_qty = 0.0

        return False

    def modify_stop_loss(self, trader, market_id, price):
        if self.stop_oid:
            # cancel the stop order and create a new one
            if trader.cancel_order(self.stop_oid):
                self.stop_ref_oid = None
                self.stop_oid = None
            else:
                return False

        if self.e == self.x:
            # all entry qty is filled
            return True

        if self.e < self.x:
            # something wrong but its ok
            return False

        if self.e > 0:
            # only if filled entry partially or totally
            order = Order(self, market_id)
            order.direction = self.direction
            order.order_type = Order.ORDER_STOP
            order.reduce_only = True
            order.quantity = self.e - self.x  # remaining
            order.order_price = price

            trader.set_ref_order_id(order)
            self.stop_ref_oid = order.ref_order_id

            self._stats['exit-maker'] = not order.is_market()

            if trader.create_order(order):  
                self.stop_oid = order.order_id
                self.stop_order_qty = order.quantity

                self.sl = price

                return True
            else:
                self.stop_ref_oid = None
                self.stop_order_qty = 0.0

        return False

    def close(self, trader, market_id):
        """
        Close the position and cancel the related orders.
        """
        if self.create_oid:
            # cancel the remaining buy order
            if trader.cancel_order(self.create_oid):
                self.create_ref_oid = None
                self.create_oid = None

                self._entry_state = StrategyTrade.STATE_CANCELED

        if self.stop_oid:
            # cancel the stop order
            if trader.cancel_order(self.stop_oid):
                self.stop_ref_oid = None
                self.stop_oid = None

        if self.limit_oid:
            # cancel the limit order
            if trader.cancel_order(self.limit_oid):
                self.limit_ref_oid = None

        if self.e == self.x:
            # all entry qty is filled
            return True

        if self.e < self.x:
            # something wrong but its ok
            return False

        order = Order(trader, market_id)
        order.direction = -self.dir  # neg dir
        order.order_type = Order.ORDER_MARKET
        order.quantity = self.e - self.x  # remaining qty

        # generated a reference order id
        trader.set_ref_order_id(order)
        self.stop_ref_oid = order.ref_order_id

        self._stats['exit-maker'] = not order.is_market()

        if trader.create_order(order):
            return True
        else:
            self.stop_ref_oid = None
            return False

        return True

    def order_signal(self, signal_type, data, ref_order_id, instrument):
        if signal_type == Signal.SIGNAL_ORDER_OPENED:
            # already get at the return of create_order
            if ref_order_id == self.create_ref_oid:
                self.create_oid = data['id']

                # init created timestamp at the create order open
                self.eot = data['timestamp']

                if data.get('stop-loss'):
                    self.sl = data['stop-loss']

                if data.get('take-profit'):
                    self.tp = data['take-profit']

                self._entry_state = StrategyTrade.STATE_OPENED

            elif ref_order_id == self.stop_ref_oid:
                self.stop_oid = data['id']

                self.xot = data['timestamp']
                # self._exit_state = StrategyTrade.STATE_OPENED

            elif ref_order_id == self.limit_ref_oid:
                self.limit_oid = data['id']

                self.xot = data['timestamp']
                # self._exit_state = StrategyTrade.STATE_OPENED

        elif signal_type == Signal.SIGNAL_ORDER_DELETED:
            # order is no longer active
            if data == self.create_oid:
                self.create_ref_oid = None                
                self.create_oid = None
                self._entry_state = StrategyTrade.STATE_DELETED

            elif data == self.limit_oid:
                self.limit_ref_oid = None
                self.limit_oid = None

            elif data == self.stop_oid:
                self.stop_ref_oid = None
                self.stop_oid = None

        elif signal_type == Signal.SIGNAL_ORDER_CANCELED:
            # order is no longer active
            if data == self.create_oid:
                self.create_ref_oid = None                
                self.create_oid = None
                self._entry_state = StrategyTrade.STATE_CANCELED

            elif data == self.limit_oid:
                self.limit_ref_oid = None
                self.limit_oid = None

            elif data == self.stop_oid:
                self.stop_ref_oid = None
                self.stop_oid = None

        elif signal_type == Signal.SIGNAL_ORDER_UPDATED:
            # order price/qty modified, cannot really be used because the strategy might
            # cancel the trade or create another one.
            # for the qty we could have a remaining_qty member, then comparing
            pass

        elif signal_type == Signal.SIGNAL_ORDER_TRADED:
            # order fully or partially filled
            filled = 0

            if data['id'] == self.create_oid:
                # a single order for the entry, then its OK and prefered to uses cumulative-filled and avg-price
                # because precision comes from the broker
                if data.get('cumulative-filled') is not None and data['cumulative-filled'] > 0:
                    filled = data['cumulative-filled'] - self.e  # compute filled qty
                elif data.get('filled') is not None and data['filled'] > 0:
                    filled = data['filled']
                else:
                    filled = 0                    

                if data.get('avg-price') is not None and data['avg-price'] > 0:
                    # in that case we have avg-price already computed
                    self.aep = data['avg-price']

                elif data.get('exec-price') is not None and data['exec-price'] > 0:
                    # compute the average entry price
                    self.aep = ((self.aep * self.e) + (data['exec-price'] * filled)) / (self.e + filled)
                else:
                    self.aep = self.op

                # cumulative filled entry qty
                if data.get('cumulative-filled') is not None:
                    self.e = data.get('cumulative-filled')
                else:
                    self.e += filled

                # logger.info("Entry avg-price=%s cum-filled=%s" % (self.aep, self.e))

                if self.e >= self.oq:
                    self._entry_state = StrategyTrade.STATE_FILLED

                    # bitmex does not send ORDER_DELETED signal, cleanup here
                    self._create_oid = None
                    self._create_ref_oid = None
                else:
                    self._entry_state = StrategyTrade.STATE_PARTIALLY_FILLED

            elif data['id'] == self.limit_oid or data['id'] == self.stop_oid:
                # either we have 'filled' component (partial qty) or the 'cumulative-filled' or the twices
                if data.get('cumulative-filled') is not None and data['cumulative-filled'] > 0:
                    filled = data['cumulative-filled'] - self.x   # computed filled qty
                elif data.get('filled') is not None and data['filled'] > 0:
                    filled = data['filled']
                else:
                    filled = 0

                if data.get('avg-price') is not None and data['avg-price'] > 0:
                    # recompute profit-loss
                    if self.dir > 0:
                        self.pl = (data['avg-price'] - self.aep) / self.aep
                    elif self.dir < 0:
                        self.pl = (self.aep - data['avg-price']) / self.aep

                    # in that case we have avg-price already computed
                    self.axp = data['avg-price']

                elif data.get('exec-price') is not None and data['exec-price'] > 0:
                    # increase/decrease profit/loss (over entry executed quantity)
                    if self.dir > 0:
                        self.pl += ((data['exec-price'] * filled) - (self.aep * self.e)) / (self.aep * self.e)
                    elif self.dir < 0:
                        self.pl += ((self.aep * self.e) - (data['exec-price'] * filled)) / (self.aep * self.e)

                    # compute the average exit price
                    self.axp = ((self.axp * self.x) + (data['exec-price'] * filled)) / (self.x + filled)

                # cumulative filled exit qty
                if data.get('cumulative-filled') is not None:
                    self.x = data.get('cumulative-filled')
                else:
                    self.x += filled

                logger.info("Exit avg-price=%s cum-filled=%s" % (self.axp, self.x))

                if self.x >= self.oq:
                    self._exit_state = StrategyTrade.STATE_FILLED

                    # bitmex does not send ORDER_DELETED signal, cleanup here
                    if data['id'] == self.limit_oid:
                        self._limit_oid = None
                        self._limit_ref_oid = None
                    elif data['id'] == self.stop_oid:
                        self._stop_oid = None
                        self._stop_ref_oid = None
                else:
                    self._exit_state = StrategyTrade.STATE_PARTIALLY_FILLED

    def position_signal(self, signal_type, data, ref_order_id, instrument):
        if signal_type == Signal.SIGNAL_POSITION_DELETED:
            # no longer related position, have to cleanup any related trades in case of manual close, liquidation
            self.position_id = None

            # it depends of the order of the position deleted...
            # @todo in some case not a good idea
            self.create_oid = None
            self.create_ref_oid = None

            if self.x < self.e:
                # mean fill the rest (because qty can concerns many trades...)
                filled = self.e - self.x

                if data.get('exec-price') is not None and data['exec-price'] > 0:
                    # increase/decrease profit/loss (over entry executed quantity)
                    if self.dir > 0:
                        self.pl += ((data['exec-price'] * filled) - (self.aep * self.e)) / (self.aep * self.e)
                    elif self.dir < 0:
                        self.pl += ((self.aep * self.e) - (data['exec-price'] * filled)) / (self.aep * self.e)

            self._exit_state = StrategyTrade.STATE_FILLED

    def is_target_order(self, order_id, ref_order_id):
        if order_id and (order_id == self.create_oid or order_id == self.stop_oid or order_id == self.limit_oid):
            return True

        if ref_order_id and (ref_order_id == self.create_ref_oid or ref_order_id == self.stop_ref_oid or ref_order_id == self.limit_ref_oid):
            return True

        return False

    def is_target_position(self, position_id, ref_order_id):
        if position_id and (position_id == self.position_id):
            return True

        if ref_order_id and (ref_order_id == self.create_ref_oid):
            return True

    def is_closing(self):
        return (self.limit_ref_oid or self.stop_ref_oid) or self._exit_state == StrategyTrade.STATE_OPENED or self._exit_state == StrategyTrade.STATE_PARTIALLY_FILLED

    #
    # persistance
    #

    def dumps(self):
        data = super().dumps()

        data['create-ref-oid'] = self.create_ref_oid
        data['stop-ref-oid'] = self.stop_ref_oid
        data['limit-ref-oid'] = self.limit_ref_oid

        data['create-oid'] = self.create_oid
        data['stop-oid'] = self.stop_oid
        data['limit-oid'] = self.limit_oid

        data['position-id'] = self.position_id

        data['stop-order-qty'] = self.stop_order_qty
        data['limit-order-qty'] = self.limit_order_qty

        return data

    def loads(self, data, strategy_service):
        if not super().loads(data, strategy_service):
            return False

        self.create_ref_oid = data.get('create-ref-oid')
        self.stop_ref_oid = data.get('stop-ref-oid')
        self.limit_ref_oid = data.get('limit-ref-oid')

        self.create_oid = data.get('create-oid')
        self.stop_oid = data.get('stop-oid')
        self.limit_oid = data.get('limit-oid')

        self.position_id = data.get('position-id')

        self.stop_order_qty = data.get('stop-order-qty', 0.0)
        self.limit_order_qty = data.get('limit-order-qty', 0.0)

        return True
