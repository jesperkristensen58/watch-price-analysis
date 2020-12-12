"""Build a scraper to collect historical watch prices.

@author Jesper Kristensen
2020
"""
import arrow
import os
import pickle
import requests
from bs4 import BeautifulSoup
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


if os.path.isfile("watch_prices.pkl"):
    # leverage a local cache so we don't re-download every time
    with open("watch_prices.pkl", "rb") as fd:
        df = pickle.load(fd)
else:
    global dict_inflations
    dict_inflations = dict()

    def inflation(fromyear=None):
        """Compute inflation multiplier for a given year in relation to 2020.

        Example:
            >> inflation(1950)
            10.89

        This means 1 dollar in 1950 is equal to 10.89 dollars in 2020.

        :param fromyear: Which year to compute multiplier for in relation to 2020.
        :return: The inflation multiplier - what each dollar in the "fromyear" is equivalent to in 2020.
        """
        global dict_inflations

        if fromyear in dict_inflations:
            return dict_inflations[fromyear]

        if fromyear == "2020":
            return 1.0

        theurl = f"https://www.dollartimes.com/inflation/inflation.php?amount=1&year={fromyear}"
        soup = BeautifulSoup(requests.get(theurl).content, "html.parser")
        multiplier = float(soup.findAll("div", attrs={'id': 'results'})[0].find("div").text.replace("$", ""))

        dict_inflations[fromyear] = multiplier

        return multiplier

    assert inflation(2016) == 1.09
    assert inflation(1950) == 10.89

    # get watch price history data
    theurl = "https://www.minus4plus6.com/PriceEvolution.php"
    soup = BeautifulSoup(requests.get(theurl).content, "html.parser")

    datestmp = soup.findAll('tr', attrs={'class': 'xl3412260'})[0].contents[3::2]
    dateslist = [d.text for d in datestmp]
    dateslist[0] = "Jan-" + dateslist[0]
    dateslist[1] = "Jan-" + dateslist[1]

    dates = [arrow.get(dateslist[0], "MMM-YYYY").datetime,
             arrow.get(dateslist[1], "MMM-YYYY").datetime,]
    dates.extend([arrow.get(d, "MMM-YY").datetime for d in dateslist[2:]])

    years = [d.strftime("%Y") for d in dates]
    dates = [d.strftime("%b-%Y") for d in dates]

    watchdetails = soup.findAll('tr')

    names = []
    all_df = []
    for thiswatch in watchdetails[1:-2]:
        # loop over each watch
        print(f"Processing watch...")

        alltds = thiswatch.findAll("td")
        watchname = None
        all_prices_this_watch = []
        for j, thistd in enumerate(alltds):

            if not watchname:
                watchname = thistd.text
                names.append(watchname)
                continue

            price = thistd.text
            if "$" in price:
                def converter(x):
                    return x.replace("$", "").replace(",", "").replace("*", "")

                if "/" in price:
                    thisprice = min(list(map(lambda x: converter(x), price.split("/"))))
                else:
                    thisprice = converter(price)

                # now adjust for inflation
                multiplier = inflation(years[j - 1])
                print(f"  multiplier = {multiplier}")
                thisprice = float(thisprice) * multiplier

                all_prices_this_watch.append(thisprice)
            else:
                all_prices_this_watch.append(None)

        df = pd.DataFrame(data=[all_prices_this_watch], index=[watchname], columns=dates)

        all_df.append(df)

    df = pd.concat(all_df)

    with open("watch_prices.pkl", "wb") as fd:
        pickle.dump(df, fd)

# analyze price changes
all_pls = []
all_p_changes = []
all_changes = []
watch_names = []
first_date = []
for watch_name, prices in df.iterrows():

    # these_prices = prices.dropna(how="any")
    p_and_l = prices.pct_change() * 100
    p_and_l.fillna(0, inplace=True)

    this_df = pd.DataFrame(data=[p_and_l], index=[watch_name])
    all_pls.append(this_df)

    # get prices vs time (with first price subtracted)
    first_price = prices.dropna(how="any").iloc[0]
    price_change_vs_first = prices - first_price

    # price_change_vs_first.dropna(how="any", inplace=True)

    this_df = pd.DataFrame(data=[price_change_vs_first], index=[watch_name])
    all_p_changes.append(this_df)

    all_changes.append(this_df.T.dropna(how="any").iloc[-1].values[0])

    watch_names.append(watch_name)
    first_date.append(this_df.T.dropna(how="any").iloc[0].name)

df_p_and_l = pd.concat(all_pls)
df_p_changes = pd.concat(all_p_changes)

# largest change:
indices = np.argsort(all_changes)[::-1]

# print top N to console
N = 10
for jj, ix in enumerate(indices):
    name = watch_names[ix]
    change = all_changes[ix]
    this_first_date = first_date[ix]

    print(f"{name}: {change} (first date = {this_first_date})")

    if jj >= N:
        break

# Plot the price histories together
plt.figure(1)
df_p_and_l.T.plot()
plt.ylim(-50, 100)
plt.gca().get_legend().remove()  # you can re-enable the legend to see all price names

plt.figure(2)
df_p_changes.T.plot()
plt.gca().get_legend().remove()
plt.grid()
plt.axhline(0, linestyle="-", color="k")
plt.xlabel("Date")
plt.ylabel("Price ($)")
plt.ylim(-1000, plt.gca().get_ylim()[1])

plt.show()
