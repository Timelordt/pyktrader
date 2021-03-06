#-*- coding:utf-8 -*-
#from base import *
from misc import *
from strategy import *
 
class DTTrader(Strategy):
    def __init__(self, name, underliers, volumes, agent = None, trade_unit = [], ratios = [], lookbacks=[], daily_close = False, email_notify = None):
        Strategy.__init__(self, name, underliers, volumes, trade_unit, agent, email_notify)
        self.lookbacks = lookbacks
        numAssets = len(underliers)
        self.ratios = [[0.7,0.7]] * numAssets
        if len(ratios) > 1:
            self.ratios = ratios
        elif len(ratios) == 1: 
            self.ratios = ratios * numAssets
        if len(lookbacks) > 0:
            self.lookbacks = lookbacks
        else: 
            self.lookbacks = [0] * numAssets
        self.tday_open = [0.0] * numAssets
        self.cur_rng = [0.0] * numAssets
        self.order_type = OPT_LIMIT_ORDER
        self.daily_close_buffer = 3
        self.close_tday = [False] * numAssets
        if len(daily_close) > 1:
            self.close_tday = daily_close
        elif len(daily_close) == 1: 
            self.close_tday = daily_close * numAssets 
        self.num_tick = 2

    def initialize(self):
        self.load_state()
        for idx, underlier in enumerate(self.underliers):
            inst = underlier[0]
            ddf = self.agent.day_data[inst]
            win = self.lookbacks[idx]
            if win > 0:
                self.cur_rng[idx] = max(max(ddf.ix[-win:,'high'])- min(ddf.ix[-win:,'close']), max(ddf.ix[-win:,'close']) - min(ddf.ix[-win:,'low']))
            else:
                self.cur_rng[idx] = max(max(ddf.ix[-2:,'high'])- min(ddf.ix[-2:,'close']), max(ddf.ix[-2:,'close']) - min(ddf.ix[-2:,'low']))
                self.cur_rng[idx] = max(self.cur_rng[idx] * 0.5, ddf.ix[-1,'high']-ddf.ix[-1,'close'],ddf.ix[-1,'close']-ddf.ix[-1,'low'])
            min_id = self.agent.instruments[inst].last_tick_id/1000
            min_id = int(min_id/100)*60 + min_id % 100 - self.daily_close_buffer
            self.last_min_id[idx] = int(min_id/60)*100 + min_id % 60
        self.save_state()
        return

    def save_local_variables(self, file_writer):
        for idx, underlier in enumerate(self.underliers):
            inst = underlier[0]
            row = ['CurrRange', str(inst), self.cur_rng[idx]]
            file_writer.writerow(row)
        return
    
    def load_local_variables(self, row):
        if row[0] == 'CurrRange':
            inst = str(row[1])
            idx = self.get_index([inst])
            if idx >= 0:
                self.cur_rng[idx] = float(row[2])
        return
        
    def run_min(self, inst):
        pass
        
    def run_tick(self, ctick):
        inst = ctick.instID
        min_id = ctick.tick_id/1000.0
        tday_open = self.agent.cur_day[inst]['open']
        idx = self.get_index([inst]) 
        if idx < 0:
            self.logger.warning('the inst=%s is not in this strategy = %s' % (inst, self.name))
            return
        if self.update_positions(idx):
            self.save_state()
        num_pos = len(self.positions[idx])
        buysell = 0
        if num_pos > 1:
            if len(self.submitted_pos[idx]) == 0:
                self.logger.warning('something wrong with position management - submitted trade is empty but trade position is more than 1')
            elif (min_id >= self.last_min_id[idx]):
                for etrade in self.submitted_pos[idx]:
                    self.speedup(etrade)                
            return
        elif num_pos == 1:
            buysell = self.positions[idx][0].direction
        if (tday_open <= 0.0) or (self.cur_rng[idx] <= 0):
            self.logger.warning("warning: open price =0.0 or range = 0.0 for inst=%s for stat = %s" % (inst, self.name))
            return
        tick_base = self.agent.instruments[inst].tick_base
        buy_trig  = tday_open + self.ratios[idx][0] * self.cur_rng[idx]
        sell_trig = tday_open - self.ratios[idx][1] * self.cur_rng[idx]
        curr_price = (ctick.askPrice1+ctick.bidPrice1)/2.0
        if (tday_open <= 0.0) or (self.cur_rng[idx] <= 0) or (curr_price <= 0.001):
            self.logger.warning("warning: open price =0.0 or range = 0.0 or curr_price=0 for inst=%s for stat = %s" % (inst, self.name))
            return
        if (min_id >= self.last_min_id[idx]):
            if (buysell!=0) and (self.close_tday[idx]):
                if (len(self.submitted_pos[idx]) <= 0):
                    msg = 'DT to close position before EOD for inst = %s, direction=%s, volume=%s, current tick_id = %s' \
                                    % (inst, buysell, self.trade_unit[idx], min_id)
                    self.close_tradepos(idx, self.positions[idx][0], curr_price - buysell * self.num_tick * tick_base)
                    self.status_notifier(msg)
                    self.save_state()
                else:
                    for etrade in self.submitted_pos[idx]:
                        print "need to speed up"
                        self.speedup(etrade)
            return
        if len(self.submitted_pos[idx]) > 0:
            return
        if ((curr_price >= buy_trig) and (buysell <=0)) or ((curr_price <= sell_trig) and (buysell >=0)):
            if buysell!=0:
                msg = 'DT to close position for inst = %s, open= %s, buy_trig=%s, sell_trig=%s, curr_price= %s, direction=%s, volume=%s' \
                                    % (inst, tday_open, buy_trig, sell_trig, curr_price, buysell, self.trade_unit[idx])
                self.close_tradepos(idx, self.positions[idx][0], curr_price - buysell * self.num_tick * tick_base)
                self.status_notifier(msg)
            if  (curr_price >= buy_trig):
                buysell = 1
            else:
                buysell = -1
            msg = 'DT to open position for inst = %s, open= %s, buy_trig=%s, sell_trig=%s, curr_price= %s, direction=%s, volume=%s' \
                                    % (inst, tday_open, buy_trig, sell_trig, curr_price, buysell, self.trade_unit[idx])
            self.open_tradepos(idx, buysell, curr_price + buysell * self.num_tick * tick_base)
            self.status_notifier(msg)
            self.save_state()
        return 
        
    def update_trade_unit(self):
        pass
