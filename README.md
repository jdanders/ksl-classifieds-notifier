The core module for this project was derived from this [gist](https://gist.github.com/blakev/a6bbe3b5a861d64c6e36) by blakev.

I updated the soup searches to match KSL server changes and added the infinite loop and email to turn this into a KSL classifieds notification generator.

This script is dependent on python3, BeautifulSoup, and KSL server responses. 
- To install BeautifulSoup in debian-based Linux: `sudo apt install python3-bs4`.
- If the KSL server changes page formatting, this script will break. Please fix it and do a pull request.


### Usage:

`./ksl_notify.py --email [your_email_address] --logfile [daemon log file location] search_term`

That will check KSL Classifieds every 10 minutes until killed and send `your_email_address` an email everytime it finds a new match for your `search_term`. Activity will be logged to `daemon log file location`. The first email will include all the current matches and be sent immediately.

Help:
```
./ksl_notify.py --help
usage: ksl_notify.py [-h] [-x] [-c CATEGORY] [-u SUBCATEGORY] [-m MIN_PRICE] [-M MAX_PRICE] [-z ZIP] [--city CITY] [--state STATE] [-d MILES] [-n PERPAGE] [-r] [-s] [--email EMAIL] [--to-email TO_EMAIL]
                     [--exception-email EXCEPTION_EMAIL] [--smtpserver SMTPSERVER] [-t [TIME]] [-H HEAD] [-C CHAR_LIMIT] [-X] [-L LOAD] [-S SAVE] [-l LOGFILE] [--loglevel LOGLEVEL] [-f]
                     [-e EMAIL_EXCEPTIONS]
                     query [query ...]

ksl_notify - command line utility to notify of new KSL classifieds ads

positional arguments:
  query                 List of terms to search on KSL classifieds. Use quotes for multiword searches

optional arguments:
  -h, --help            show this help message and exit
  -x, --expand-search   Include listings more broadly related to your search terms.
  -c CATEGORY, --category CATEGORY
                        Category to apply to search results
  -u SUBCATEGORY, --subcategory SUBCATEGORY
                        Category to apply to search results
  -m MIN_PRICE, --min-price MIN_PRICE
                        Minimum dollar amount to include in search results
  -M MAX_PRICE, --max-price MAX_PRICE
                        Maximum dollar amount to include in search results
  -z ZIP, --zip ZIP     ZIP code around which to center search results
  --city CITY           City around which to center search results
  --state STATE         State (abbr, like UT) around which to center search results
  -d MILES, --miles MILES
                        Maximum distance in miles from ZIP code center
  -n PERPAGE, --perPage PERPAGE
                        Number of results to include in search results.(Does not seem to work!)
  -r, --reverse         If included, query will sort oldest to newest. Default is newest to oldest
  -s, --sold            If included, query will return results for sold items as well as active items
  --email EMAIL         email address to send emails from. If --to-email is not specified, this email will also be used as the receiver of the email.
  --to-email TO_EMAIL   email address to send the email to. Defaults to --email value.
  --exception-email EXCEPTION_EMAIL
                        email address to send exception emails to. Defaults to --email value.
  --smtpserver SMTPSERVER
                        email SMTP server:port, should be unneeded for gmail, outlook, hotmail, msn, yahoo, or comcast
  -t [TIME], --time [TIME]
                        Number of minutes to wait between searches
  -H HEAD, --head HEAD  Number of lines to include from the listing's description. If not specified, the entire description will be included.
  -C CHAR_LIMIT, --char-limit CHAR_LIMIT
                        Number of characters allowed in the message body. Listings that exceed the character count will be sent in additional messages.
  -X, --exclude-links   Exclude links from message.
  -L LOAD, --load LOAD  Load seen listings from a JSON file. Format is a dictionary of query search terms to listing links.
  -S SAVE, --save SAVE  Save seen listings to a JSON file.
  -l LOGFILE, --logfile LOGFILE
                        File to log output from daemon process, defaults to stdout
  --loglevel LOGLEVEL   Choose level: debug, info, warning
  -f, --foreground      Do not fork to background
  -e EMAIL_EXCEPTIONS, --email-exceptions EMAIL_EXCEPTIONS
                        Number of repeated exceptions before sending emails
```

### Advanced Usage:

Most filters available on the KSL webpage are made available through the script. Here's an example:

```
./ksl_notify.py iphone galaxy --email sender@example.com --to-email receiver@example.com --smtpserver "smtp.example.com:587" -l /tmp/ksl_iphone_log.log --foreground --category Electronics --subcategory "Cell Phones Unlocked" --min-price 100 --max-price 250 --zip 84111 --miles 35 --time 60
```

This will send listing emails from `sender@example.com` to `receiver@example.com` that match "iphone" or "galaxy" searches in "Unlocked Cell Phones" underneath "Electronics" category that cost between $100-$250 within 35 miles of zip code 84111. It will check once per hour.

### Design:

The core KSL class is responsible for fetching and parsing the HTML that the KSL classified server returns. For each query it builds up a query string, submits that to the server, and then uses BeautifulSoup to parse the result. You can run a query through just the KSL class by running something like `python3 ksl.py iphone`

The ksl_notify script handles all of the surrounding bookkeeping regarding tracking new listings, generating email, and handling exceptions.

If (when) the script becomes outdated, the primary parts to fix will be the names of the `div`s in the `find_elements` function of the KSL class, or the names of the query strings used in the `build_qs` function. Most of the query strings are built directly from the parameter names, which are defined at the bottom of the two files. 

The script is designed to run as a background process. The most awkward part about that decision is that you have to search your running processes to kill a query you don't care about any more.

As a background process, it is designed to be resilient to exceptions. As such, there is a running count of exception incidents, starting at 0, incrementing by 10 for each exception, and decrementing by 1 for each successful loop. If there's a serious problem (internet down, KSL server change, etc) the script will stop after the count exceeds 100. If there are infrequent issues (socket timeout), it will plow through those events and notify the email of the event unless the loglevel disables it.

### Possible improvements:

Add a callback of some kind to allow user to add custom filtering on results before deciding whether to email the result.

Migrate from BeautifulSoup and urlopen to a more resilient session model that acts more like a visitor to sell.ksl.com would. Not likely since I can't guarantee it would be more resilient. Alternatively figure out how to use the API that the KSL Classified app uses. That should work more consistently than any scraping.

### Compliance with KSL Terms of Use

Please do not use the script if it violates KSL Classifieds Terms of Use, currently found [here](http://www.ksl.com/?nid=391&sid=848020). You may also need to consider the ksl.com site Terms of Use, currently found [here](http://www.ksl.com/?sid=95313&nid=250). I am not a lawyer and can offer no advice on the appropriate use of this script and I am not liable for your use of this script.
