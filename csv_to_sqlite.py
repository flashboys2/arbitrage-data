import os

os.system('sqlite3 data/arbitrage_new.db ".mode csv" ".import data/block_fees.csv block_fees" ".import data/eth.csv eth_data" ".import data/all_logs_bigquery.csv logs" ".import data/block_data.csv blocks" ".import data/all_success_arb_txs_bigquery.csv success" ".import data/all_inclfail_arb_txs_bigquery.csv wfail" ".import data/auctions.csv auctions" ".import data/profits.csv profits" "CREATE TABLE mergedprofitabletxs AS SELECT *,substr(timestamp,0,11) as date FROM wfail LEFT JOIN profits on profits.txhash=wfail.transaction_hash LEFT JOIN success on success.transaction_hash=wfail.transaction_hash LEFT JOIN blocks on blocks.number=wfail.block_number GROUP BY wfail.transaction_hash ORDER BY wfail.rowid ASC;" ".quit" ""')
os.system('mv data/arbitrage_new.db data/arbitrage.db')
