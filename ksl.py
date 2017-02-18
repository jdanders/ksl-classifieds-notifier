import re
import argparse
import concurrent.futures
import string

from collections import namedtuple
from urllib.request import urlopen
from urllib.parse import urlencode, urljoin

from bs4 import BeautifulSoup


Listing = namedtuple('Listing', 'title city state age price link description')


class KSL(object):
    URL = 'http://ksl.com/classifieds/search?'

    # Extra query string entries
    URL_QS = {
        'nocache': 1,            # don't cache results, FRESH!
    }

    def __init__(self):
        self.thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)

    def __do_request(self, args):
        if len(args) == 2:
            query, url = args
            timeout = 5  # seconds
        else:
            query, url, timeout = args
        return (query, urlopen(url, timeout=timeout).read(), )

    def search(self, query, **etc):
        with self.thread_pool as ex:
            # perform every search using the thread pool executor
            yield from ex.map(self.__do_request, self.build_qs(query, **etc))

    def find_elements(self, html):
        soup = BeautifulSoup(html, 'html.parser')

        for ad_box in soup.find_all('div', class_='listing'):
            if 'featured' in ad_box.attrs['class']:
                continue
            links = ad_box.find_all('a', class_='link')

            # get the listing title
            if links:
                #    and clean it up...
                title = links[0].text.strip(string.punctuation)
                title = [t.capitalize() for t in title.split() if len(t) > 3]
                title = ' '.join(title)
                link = urljoin(self.URL, links[0].get('href'))
            else:
                continue

            # get the price
            price_box = ad_box.find('h3', class_='price')

            # ignore prices that "don't exist"
            if not price_box or price_box.text.count('-') >= 6:
                continue
            else:
                price = price_box.text.strip()

            # get the location
            ad_detail = ad_box.find('div', class_='listing-detail-line')
            location = ad_detail.find('span', class_='address').text
            location = location.encode('ascii', 'ignore')
            location = location.decode('utf-8')
            location = location.split(',')

            #    get the city and state, clean up the city from formatting
            city, state = location[0].strip(), location[-1].strip().upper()
            city = ' '.join([p.capitalize() for p in city.split()])

            #    get the age of the posting
            lifespan = ad_detail.find('span', class_='timeOnSite').text.strip()
            lifespan = lifespan.encode('ascii', 'ignore').split(b'|')[-1]
            lifespan = lifespan.strip().decode('ascii')

            #    get the description
            description = ad_box.find('div', class_='description-text')
            # Remove the 'more ...' text after the link to more...
            linktxt = description.find('a').text
            description = description.text.replace(linktxt, '').strip()
            description = description.encode('ascii', 'ignore').decode('utf-8')

            yield Listing(title, city, state, lifespan,
                          price, link, description)

    def build_qs(self, queries, **etc):
        for query in queries:
            args = etc.copy()
            # ensure we always have a minimum price, of at least $0
            minp = max(0, int(args.pop('min_price', '0')))

            maxp = max(0, int(args.pop('max_price', '0')))
            # if we have a minimum and maximum price
            # then we want to make sure the lower value is set to `minp`
            if minp and maxp:
                minp, maxp = sorted([minp, maxp])
            minp = None if minp == 0 else minp
            maxp = None if maxp == 0 else maxp

            # If city, assure state exists
            if (('city' in args and args['city'])
                    and ('state' not in args or not args['state'])):
                args['state'] = 'UT'

            qs = {
                'keyword': query,
                'priceFrom': minp,
                'priceTo': maxp,
            }

            # apply defaults
            qs.update(self.URL_QS)

            # fill in any additional parameters
            # that were passed, but not explicitly handled
            for k, value in args.items():
                qs.setdefault(k, value)

            # Remove None values
            qs = {k: v for k, v in qs.items() if v is not None}

            # encode
            qs = urlencode(qs)
            queryurl = '{}&{}'.format(self.URL, qs)
            yield (query, queryurl, )

    def listing(id):
        pass


def gather_report(query_result):
    report = ""
    for result in query_result:
        report += ('{result.title} - {result.price} - {result.age} : '
                   '{result.city}, {result.state}\n'
                   '   {result.link}\n'
                   '   {result.description}\n\n'.format(**locals()))
    return report


def main(args):
    if args.get('query') is None:
        return

    # create the thin object
    ksl = KSL()

    # find our results
    queries = args.pop('query')
    for query, html_data in ksl.search(queries, **args):
        query_result = ksl.find_elements(html_data)
        report = gather_report(query_result)
        if report:
            if len(queries) > 1:
                print ("** Search for %s **" % query)
            print (report)


if __name__ == '__main__':
    p = argparse.ArgumentParser(
        description='ksl - command line utility to query KSL classifieds'
    )

    p.add_argument('query', nargs='+', action='store', default=None,
                   help='List of terms to search on KSL classifieds. '
                   'Use quotes for multiword searches')
    p.add_argument('-c', '--category', default=None,
                   help='Category to apply to search results')
    p.add_argument('-u', '--subcategory', default=None, dest='subCategory',
                   help='Category to apply to search results')
    p.add_argument('-m', '--min-price', default='0',
                   help='Minimum dollar amount to include in search results')
    p.add_argument('-M', '--max-price', default='0',
                   help='Maximum dollar amount to include in search results')
    p.add_argument('-z', '--zip', default=None,
                   help='ZIP code around which to center search results')
    p.add_argument('--city', default=None,
                   help='City around which to center search results')
    p.add_argument('--state', default=None,
                   help='State (abbr, like UT) around which to center search '
                   'results')
    p.add_argument('-d', '--miles', default=None,
                   help='Maximum distance in miles from ZIP code center')
    p.add_argument('-n', '--perPage', default=None,
                   help='Number of results to include in search results.'
                   '(Does not seem to work!)')
    p.add_argument('-r', '--reverse', action='store_const',
                   default=0, const=1, dest='sort',
                   help='If included, query will sort oldest to newest. '
                   'Default is newest to oldest')
    p.add_argument('-s', '--sold', action='store_const', default=0, const=1,
                   help='If included, query will return results for sold '
                   'items as well as active items')

    args = p.parse_args()

    # do it
    main(vars(args))
