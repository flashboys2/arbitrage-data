from sqlite_adapter import query_db
import json
from datetime import datetime
import numpy as np

PRINCETON_TEMPLATE = open('graph_templates/princeton1.tex').read()
BREADTH_SCATTER_TEMPLATE = open('graph_templates/breadth_scatter.tex').read()
LINE_TEMPLATE = open('graph_templates/date_line.tex').read()

COORDS_CONSTANT = "\\addplot+ coordinates {%coords%};"
HIST_COORDS = "\\addplot+[only marks, scatter,opacity=0.1,mark=*] coordinates {%coords%};"
buckets = {}

def init_dict(d,k,v):
    if not k in d:
        d[k] = v

def get_princeton_graph_tikz(desiredsize):
    results = query_db("SELECT SUM(CAST(eth_profit as FLOAT)) as total_profit,mergedprofitabletxs.block_number as block_number,total_fees,substr(timestamp,0,11) as date FROM mergedprofitabletxs LEFT JOIN block_fees ON block_fees.block_number=mergedprofitabletxs.block_number WHERE all_positive='True' GROUP BY mergedprofitabletxs.block_number ORDER BY CAST(total_profit as FLOAT) DESC LIMIT %d;" % desiredsize)
    labels = ""
    profits = ""
    fees = ""
    rewards = ""
    dates = ""
    datespoints = ""

    for result in results:
        label = result['block_number']
        date = result['date']
        date = date.split("-")
        date = date[2] + "-" + date[1] + "-" + date[0][2:]
        if date in dates:
            date = date + " " # (dirty hack for repeated labels)
        dates += date + ", "
        datespoints += "("+  date+  ", 0) "
        labels += label +  ", "
        profits += "(" +  label +  ", " +  str(result['total_profit']) + ") "
        fees += "("+  label+  ", "+  str(result['total_fees']) + ") "
        blocknum = int(result['block_number'])
        if blocknum < 4370000:
            reward = 5
        elif blocknum < 7280000:
            reward = 3
        else:
            reward = 2
        rewards += "("+  label+  ", "+  str(reward) + ") "

    print(PRINCETON_TEMPLATE.replace("%labels%", labels).replace("%profits%", profits).replace("%fees%", fees).replace("%rewards%", rewards).replace("%dates%", dates).replace("%datespoints%", datespoints))


def get_princeton_graph_tikz_2(skip_under=0):
    block_nums = []
    results = query_db("SELECT SUM(CAST(eth_profit as FLOAT)) as eth_profit,total_fees,mergedprofitabletxs.block_number as block_number,total_fees FROM mergedprofitabletxs LEFT JOIN block_fees ON block_fees.block_number=mergedprofitabletxs.block_number WHERE all_positive='True' GROUP BY mergedprofitabletxs.block_number ORDER BY mergedprofitabletxs.block_number ASC;")
    for result in results:
        if int(result['block_number']) < skip_under:
            continue
        fees = float(result['total_fees'])
        eth_revenue = float(result['eth_profit'])
        block_nums.append(int(result['block_number']))
        ratio = eth_revenue/(eth_revenue + fees)
        bucket = float("{0:.2f}".format(ratio))
        if ratio - bucket > .00000001:
            print("adding")
            bucket += .01
        bucket = round(bucket, 2)
        bucket = str(bucket)
        print(ratio,bucket)
        if not bucket in buckets:
            buckets[bucket] = 1
        else:
            buckets[bucket] += 1


    numtotal = sum(buckets.values())
    print(buckets)

    for bucketlabel in sorted(buckets.keys(), key=float):
        #print("(%s, %f)" % (bucketlabel, float(buckets[bucketlabel])/float(numtotal)))
        print("(%s, %f)" % (bucketlabel, buckets[bucketlabel]))
    print(numtotal, max(block_nums), min(block_nums))

def get_moving_average(coords, width):
    coords = np.convolve(coords, np.ones((width,))/width, mode='same')
    return coords

def get_cumulative(coords):
    newcoords = []
    runningtotal = 0
    for i in range(len(coords)):
        runningtotal += coords[i]
        newcoords.append(runningtotal)
    return newcoords

def calculate_top(valuesdict, num):
    # return top num keys in valuesdict with highest mapped values
    # used to find top *n* arbitrage bots, exchanges, etc
    return sorted(valuesdict.keys(), key=lambda x : sum(valuesdict[x].values()), reverse=True)[:num]

def get_breadth_graphs_tikz(graphs_to_generate, skip_until='2017-09-01'):
    prices = {}
    price_data = query_db("SELECT  * FROM eth_data")
    for price_datum in price_data:
        prices[price_datum['date']] = price_datum['price(USD)']
    results = query_db("SELECT * FROM mergedprofitabletxs WHERE all_positive = 'True' AND CAST(eth_profit as FLOAT) > 0.0;")
    eth_revenues = {}
    usd_revenues = {}
    usd_profits = {}
    gas_ratios_pertx = {}
    num_trades_pertx = {}
    exchange_breakdowns_eth = {}
    bot_breakdowns_usd = {}
    bot_breakdowns_usd_profit = {}
    pertx_ratios = open('reports/data/ratios.csv', 'w')
    for result in results:
        date = result['date']
        eth_revenue = float(result['eth_profit'])
        gas_used = float(result['receipt_gas_used'])
        eth_profit = eth_revenue - ((gas_used * float(result['gas_price'])) / (10 ** 18))
        usd_revenue = eth_revenue * float (prices.get(result['date'], 0))
        usd_profit = eth_profit * float (prices.get(result['date'], 0))
        pertx_ratios.write("%f\n" % (eth_profit/eth_revenue))

        revenue_graph = json.loads(result['profit_graph'])
        num_trades = len(revenue_graph) / 2 # revenue graph contains two edges per trade
        init_dict(eth_revenues, date, 0)
        init_dict(usd_revenues, date, 0)
        init_dict(usd_profits, date, 0)
        init_dict(gas_ratios_pertx, date, [])
        init_dict(num_trades_pertx, date, [])
        eth_revenues[date] += eth_revenue
        usd_revenues[date] += usd_revenue
        usd_profits[date] += usd_profit
        gas_ratios_pertx[date].append(gas_used/num_trades)
        num_trades_pertx[date].append(num_trades)
        for edge in revenue_graph:
            if edge[0][0] == "!": # ! is a special marker for exchange node
                # each exchange will appear once with a special "!" label, in two edges in the revenue graph
                # however, it will be the source of only one edge
                exchange = edge[0][1:]

                if not exchange in exchange_breakdowns_eth:
                    exchange_breakdowns_eth[exchange] = {}
                if not date in exchange_breakdowns_eth[exchange]:
                    exchange_breakdowns_eth[exchange][date] = 0
                exchange_breakdowns_eth[exchange][date] += ((1.0/num_trades) * eth_revenue)
        bot = result['from_address']
        init_dict(bot_breakdowns_usd, bot, {})
        init_dict(bot_breakdowns_usd[bot], date, 0)
        bot_breakdowns_usd[bot][date] += usd_revenue
        init_dict(bot_breakdowns_usd_profit, bot, {})
        init_dict(bot_breakdowns_usd_profit[bot], date, 0)
        bot_breakdowns_usd_profit[bot][date] += usd_profit


    eth_revenue_coords = ""
    usd_revenue_coords = ""
    usd_profit_coords = ""
    gas_usage_coords = ""

    xs = []
    eth_revenue_ys = []
    usd_revenue_ys = []
    usd_profit_ys = []
    sorted_dates = sorted(prices.keys())
    sorted_dates = sorted_dates[sorted_dates.index(sorted(eth_revenues.keys())[0]):sorted_dates.index(sorted(eth_revenues.keys())[-3])] # (prune last 3 days for potential data quality issues)
    if skip_until is not None:
        sorted_dates = sorted_dates[sorted_dates.index(skip_until):] # trim early non-representative data
    for date in sorted_dates:
        eth_revenue_coords += "(%s,%f) " % (date, eth_revenues.get(date, 0.0))
        usd_revenue_coords += "(%s,%f) " % (date, usd_revenues.get(date, 0.0))
        usd_profit_coords += "(%s,%f) " % (date, usd_profits.get(date, 0.0))
        gas_usage_coords += "(%s,%f) [%f]" % (date, np.mean(gas_ratios_pertx.get(date, [0.0])), np.mean(num_trades_pertx.get(date, [0])))
        xs.append(date)
        eth_revenue_ys.append(float(eth_revenues.get(date, 0.0)))
        usd_revenue_ys.append(float(usd_revenues.get(date, 0.0)))
        usd_profit_ys.append(float(usd_profits.get(date, 0.0)))


    ma_eth_coords = ""
    ma_usd_coords = ""
    ma_usd_profit_coords = ""
    ma_eth_revenue=get_moving_average(eth_revenue_ys,14)
    ma_usd_revenue=get_moving_average(usd_revenue_ys,14)
    ma_usd_profit=get_moving_average(usd_profit_ys,14)

    cum_eth_graph_lines = ""
    ma_botusd_graph_lines = ""
    ma_botusd_profit_graph_lines = ""
    price_coords = ""
    cum_eth_coords = ""
    cum_usd_coords = ""
    cum_usd_profit_coords = ""
    cumulative_eth_revenue=get_cumulative(eth_revenue_ys)
    cumulative_usd_revenue=get_cumulative(usd_revenue_ys)
    cumulative_usd_profit=get_cumulative(usd_profit_ys)

    for i in range(len(xs)):
        ma_eth_coords += "(%s,%f)" % (xs[i], ma_eth_revenue[i])
        ma_usd_coords += "(%s,%f)" % (xs[i], ma_usd_revenue[i])
        ma_usd_profit_coords += "(%s,%f)" % (xs[i], ma_usd_profit[i])
        price_coords += "(%s,%f) " % (xs[i], float(prices[xs[i]]))
        cum_eth_coords += "(%s,%f) " % (xs[i], cumulative_eth_revenue[i])
        cum_usd_coords += "(%s,%f) " % (xs[i], cumulative_usd_revenue[i])
        cum_usd_profit_coords += "(%s,%f) " % (xs[i], cumulative_usd_profit[i])
    cum_eth_graph_lines += COORDS_CONSTANT.replace("addplot+", "addplot+[black]").replace("%coords%", cum_eth_coords) + "\n"
    ma_botusd_graph_lines += COORDS_CONSTANT.replace("addplot+", "addplot+[black]").replace("%coords%", ma_usd_coords) + "\n"
    ma_botusd_profit_graph_lines += COORDS_CONSTANT.replace("addplot+", "addplot+[black]").replace("%coords%", ma_usd_profit_coords) + "\n"

    top_5_exchanges = calculate_top(exchange_breakdowns_eth, 6)
    for exchange in top_5_exchanges:
        exchange_coords = ""
        exchange_revenues = []
        for i in range(len(xs)):
            exchange_revenues.append(exchange_breakdowns_eth[exchange].get(xs[i], 0))
        cumulative_exchange_revenue = get_cumulative(exchange_revenues)
        for i in range(len(xs)):
            exchange_coords += "(%s,%f) " % (xs[i], cumulative_exchange_revenue[i])
        cum_eth_graph_lines += COORDS_CONSTANT.replace("%coords%", exchange_coords) + "\n"


    top_bots = calculate_top(bot_breakdowns_usd, 10)
    # todo consolidate this + above into method
    for bot in top_bots:
        bot_revenue_coords = ""
        bot_revenues = []
        bot_profit_coords = ""
        bot_profits = []
        for i in range(len(xs)):
            bot_revenues.append(bot_breakdowns_usd[bot].get(xs[i], 0))
            bot_profits.append(bot_breakdowns_usd_profit[bot].get(xs[i], 0))
        bot_revenue_ma = get_moving_average(bot_revenues, 14)
        bot_profit_ma = get_moving_average(bot_profits, 14)
        for i in range(len(xs)):
            bot_revenue_coords += "(%s,%f) " % (xs[i], bot_revenue_ma[i])
            bot_profit_coords += "(%s,%f) " % (xs[i], bot_profit_ma[i])
        ma_botusd_graph_lines += COORDS_CONSTANT.replace("%coords%", bot_revenue_coords) + "\n"
        ma_botusd_profit_graph_lines += COORDS_CONSTANT.replace("%coords%", bot_profit_coords) + "\n"


    if "pure_revenue_eth" in graphs_to_generate:
        open('reports/pure_revenue_eth.tex', 'w').write(BREADTH_SCATTER_TEMPLATE.replace("%coords%", eth_revenue_coords).replace("%macoords%", ma_eth_coords).replace("%title%", "Pure Revenue Market Size (ETH)").replace("%ylabel%", "Daily Pure Revenue Captured (ETH)").replace("%cumcoords%", cum_eth_coords).replace("%extra%", "").replace("%max%", str(2*max(cumulative_eth_revenue))))
    if "pure_revenue_usd" in graphs_to_generate:
        open('reports/pure_revenue_usd.tex', 'w').write(BREADTH_SCATTER_TEMPLATE.replace("%coords%", usd_revenue_coords).replace("%macoords%", ma_usd_coords).replace("%title%", "Pure Revenue Market Size (USD)").replace("%ylabel%", "Daily Pure Revenue Captured (USD)").replace("%cumcoords%", cum_usd_coords).replace("%extra%", open('graph_templates/eth_price_line.tex').read().replace("%coords%", price_coords)).replace("%max%", str(2*max(cumulative_usd_revenue))))
    if "pure_revenue_exch" in graphs_to_generate:
        open('reports/pure_revenue_exch_breakdown.tex', 'w').write(LINE_TEMPLATE.replace("%plots%", cum_eth_graph_lines).replace("%legendkeys%", "Market Total," + ",".join(top_5_exchanges)).replace("%title%", "Pure Revenue Per Exchange Since 04/18").replace("%ylabel%", "Cumulative Pure Revenue Captured (ETH)").replace("%max%", str(2*max(cumulative_eth_revenue))).replace("%legendpos%", "south east").replace("%extraaxisoptions%", ", x label style={at={(0.5,-.25)},anchor=south,}"))
    if "pure_revenue_botmas" in graphs_to_generate:
        open('reports/pure_revenue_bot_revenue.tex', 'w').write(LINE_TEMPLATE.replace("%plots%", ma_botusd_graph_lines).replace("%legendkeys%", "Market Total," + ",".join([x[:8] + ".." for x in top_bots])).replace("%title%", "Pure Revenue Per Bot, 14-Day Moving Average").replace("%ylabel%", "Daily Pure Revenue Captured (USD)").replace("%max%", str(2*max(ma_usd_revenue))).replace("%legendpos%", "outer north east").replace("%extraaxisoptions%", ",enlarge x limits=-1,width=.9\\textwidth, height=0.4\\textwidth,x label style={at={(0.5,-.45)},anchor=south,}"))
        open('reports/pure_revenue_bot_profit.tex', 'w').write(LINE_TEMPLATE.replace("%plots%", ma_botusd_profit_graph_lines).replace("%legendkeys%", "Market Total," + ",".join([x[:8] + ".." for x in top_bots])).replace("%title%", "Pure Revenue Profit Per Bot, 14-Day Moving Average").replace("%ylabel%", "Daily Pure Revenue Profit (USD)").replace("%max%", str(2*max(ma_usd_profit))).replace("%legendpos%", "outer north east").replace("%extraaxisoptions%", ",enlarge x limits=-1,width=.9\\textwidth, height=0.4\\textwidth,x label style={at={(0.5,-.45)},anchor=south,}"))
    if "pure_revenue_gas_numtrades" in graphs_to_generate:
        open('reports/pure_revenue_gas.tex', 'w').write(BREADTH_SCATTER_TEMPLATE.replace("%coords%", gas_usage_coords).replace("%macoords%", "").replace("%title%", "Gas Trends in Pure Revenue").replace("%cumcoords%", "(2018-03-08, 0) (2018-03-08, 300000)").replace("%extra%", "").replace("%max%", "300000").replace("%ylabel%", "Mean Gas Used Per Trade").replace("%extraaxisoptions%", open("graph_templates/gas_extraaxisoptions.tex").read()).replace("ymode=log,", "").replace("scatter,", "scatter, only marks,"))

def get_pga_winner_graphs():
    results = query_db("SELECT *,substr(timestamp,0,11) as date FROM auctions JOIN mergedprofitabletxs ON auctions.hash=mergedprofitabletxs.transaction_hash WHERE all_positive='True' GROUP BY transaction_hash")
    revenue_file = open('reports/data/revenue.csv', 'w')
    profit_file = open('reports/data/profit.csv', 'w')
    cost_file = open('reports/data/cost.csv', 'w')
    gas_used_file = open('reports/data/gas_used.csv', 'w')
    gas_prices_file = open('reports/data/gas_prices.csv', 'w')
    for result in results:
        revenue = float(result['eth_profit'])
        gas_price = float(result['gas_price'])
        gas_used = float(result['receipt_gas_used'])
        cost = (gas_price * gas_used) / (10 ** 18)
        profit=revenue-cost
        revenue_file.write(str(revenue) + "\n")
        profit_file.write(str(profit) + "\n")
        cost_file.write(str(cost) + "\n")
        gas_used_file.write(str(gas_used) + "\n")
        gas_prices_file.write(str(gas_price) + "\n")
        print(result['txhash'], revenue, cost, profit)

def get_pga_dynamics_graphs():
    good_auctions = set()
    auction_dates = {}
    auction_profits = {}
    good_auctions_res = query_db("SELECT auction_id,eth_profit FROM auctions JOIN profits ON auctions.hash=profits.txhash WHERE all_positive='True' GROUP BY txhash")
    for auction in good_auctions_res:
        good_auctions.add(int(auction['auction_id']))
        auction_profits[int(auction['auction_id'])] = float(auction['eth_profit'])
    print(good_auctions)
    # todo consolidate w auction postprocessing code in read_csv.py; move this there or that here?
    per_auction_bot_traces = {}
    for auction_id in sorted(list(good_auctions)):
        bids = query_db("SELECT * FROM auctions WHERE auction_id='%d'" % auction_id)
        for result in bids:
            bot = result['sender']
            auction_date = datetime.utcfromtimestamp(int(result['time_seen']) / (10 ** 9)).strftime('%Y-%m-%d')
            auction_dates[int(result['auction_id'])] =  auction_date
            init_dict(per_auction_bot_traces, auction_id, {})
            init_dict(per_auction_bot_traces[auction_id], bot, [])
            per_auction_bot_traces[auction_id][bot].append(dict(result))

    sorted_bot_deltas = {}
    min_bid_ratios = []
    for auction in per_auction_bot_traces:
        for bot in per_auction_bot_traces[auction]:
            trace = per_auction_bot_traces[auction][bot]
            if len(trace) < 5:
                # no repeated bids; probably noise
                continue
            trace = sorted(trace, key=lambda x : float(x['gas_price']))
            min_bid = float(trace[0]['gas_price']) * float(trace[0]['gas_limit']) / (10 ** 18)
            profit = float(auction_profits[int(trace[0]['auction_id'])])
            min_bid_profit_ratio = min_bid/profit
            min_bid_ratios.append(min_bid_profit_ratio)

            per_auction_bot_traces[auction][bot] = trace
            init_dict(sorted_bot_deltas, auction, {})
            init_dict(sorted_bot_deltas[auction], bot, ([],[]))
            for i in range(1, len(trace)):
                try:
                    bid_price_percent_delta = round((float(trace[i]['gas_price']) - float(trace[i-1]['gas_price']))/float(trace[i-1]['gas_price']), 8) * 100
                    bid_time_delta = (float(trace[i]['time_seen']) - float(trace[i-1]['time_seen'])) / (10 ** 9)
                except:
                    print(result['auction_id'], "has a failed bid")
                    pass
                sorted_bot_deltas[auction][bot][0].append(bid_price_percent_delta)
                sorted_bot_deltas[auction][bot][1].append(bid_time_delta)

    xs = []
    median_raise_ys = []
    mean_time_delta_ys = []
    raises = []
    eth_profit_ys = []
    num_raises = []
    for auction in sorted_bot_deltas:
        for bot in sorted_bot_deltas[auction]:
            #print(auction, bot, np.mean(sorted_bot_deltas[auction][bot][1]), auction_dates[auction])
            print(auction, bot, sorted_bot_deltas[auction][bot][0], auction_dates[auction])
            raises += sorted_bot_deltas[auction][bot][0]
            xs.append(auction_dates[auction])
            eth_profit_ys.append(auction_profits[auction])
            median_raise_ys.append(np.median(sorted_bot_deltas[auction][bot][0]))
            mean_time_delta_ys.append(np.mean(sorted_bot_deltas[auction][bot][1]))
            num_raises.append(len(sorted_bot_deltas[auction][bot][1]))

    print([np.min(raises), np.max(raises), np.median(raises), np.mean(raises), np.var(raises), sum((y < .13 and y >= .12 for y in raises))], len(raises))


    median_raise_plots = ""
    time_delta_plots = ""
    median_raise_coords = ""
    time_delta_coords = ""
    for i in range(len(xs)):
        median_raise_coords += "(%s,%f) [%f] " % (xs[i], median_raise_ys[i], eth_profit_ys[i])
        time_delta_coords += "(%s,%f) [%f] " % (xs[i], mean_time_delta_ys[i], num_raises[i])
    median_raise_plots += HIST_COORDS.replace("%coords%", median_raise_coords)
    time_delta_plots += HIST_COORDS.replace("%coords%", time_delta_coords)
    open('reports/data/pga_raises.csv', 'w').write(median_raise_plots)
    median_raise_plots += " \\addplot+[red] coordinates {(%s,15.0) (%s,15.0)}; \\addplot+[green] coordinates {(%s,12.5) (%s,12.5)};" % (xs[0], xs[-1], xs[0], xs[-1]) # draw horizontal lines at model prediction through coords; hack to get around no horizontal lines in pgfplots datelib
    open('reports/median_raise_scatter.tex', 'w').write(LINE_TEMPLATE.replace("%plots%", median_raise_plots).replace("%legendkeys%", "\\\\y=15\\\\y=12.5\\\\").replace("%title%", "Raise Strategy Evolution").replace("ymode=log,", "").replace("%ylabel%", "Median Raise Percent Over Own Bid").replace("%max%", "75").replace("%legendpos%", "north east").replace("%extraaxisoptions%", open('graph_templates/median_raise_extraaxisoptions.tex').read()))
    open('reports/latency_scatter.tex', 'w').write(LINE_TEMPLATE.replace("%plots%", time_delta_plots).replace("%legendkeys%", "").replace("%title%", "Bot Latency Evolution").replace("ymode=log,", "").replace("%ylabel%", "Mean Observed Time Between Bids").replace("%max%", "75").replace("%legendpos%", "north east").replace("%extraaxisoptions%", open('graph_templates/median_raise_extraaxisoptions.tex').read()))
    min_bid_ratios_file = open('reports/data/min_bid_ratios.csv', 'w')
    for bid in min_bid_ratios:
        min_bid_ratios_file.write(str(bid) + "\n")

if __name__ == "__main__":
    #get_breadth_graphs_tikz(skip_until="2018-04-01")
    #get_breadth_graphs_tikz(["pure_revenue_gas_numtrades"], skip_until=None)
    get_breadth_graphs_tikz(["pure_revenue_eth", "pure_revenue_usd", "pure_revenue_botmas"], skip_until=None)
    #get_breadth_graphs_tikz(["pure_revenue_exch"], skip_until="2018-04-01")
    #get_pga_winner_graphs()
    #get_pga_dynamics_graphs()

    #get_princeton_graph_tikz_2()
    #get_princeton_graph_tikz_2(skip_under=7000000)
    #get_princeton_graph_tikz(20)

