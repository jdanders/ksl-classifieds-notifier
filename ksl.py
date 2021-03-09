import concurrent.futures

from collections import namedtuple
from urllib.request import urlopen, Request
from urllib.parse import urlencode, urljoin
import logging

from bs4 import BeautifulSoup
import json
from datetime import datetime, timedelta

from ksl_cli_parser import KslCliParser

Listing = namedtuple('Listing', 'title city state age price link description')


class KSL(object):
    SEARCH_URL = 'https://ksl.com/classifieds/search?'
    LIST_URL = 'https://www.ksl.com/classifieds/listing/'
    time_offset = datetime.now() - datetime.utcnow()
    time_offset = timedelta(days=time_offset.days,
                            seconds=round(time_offset.seconds/60)*60)
    QUERY_PARAM_KEYS = {
        'expandSearch',
        'keyword',
        'nocache',
        'zip',
        'miles',
        'sort',
        'sold',
        'city',
        'state',
        'priceFrom',
        'priceTo',
        'subCategory',
        'category'
    }


    # Extra query string entries
    URL_QS = {
        'nocache': 1,            # don't cache results, FRESH!
    }

    def __init__(self):
        self.thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)

    def __do_request(self, args):
        logging.debug("Performing request for args {args}".format(args=args))
        if len(args) == 2:
            query, url = args
            timeout = 5  # seconds
        else:
            query, url, timeout = args
        req = Request(
            url,
            data=None,
            headers={
                'User-Agent': ('Mozilla/5.0')
            }
        )
        return (query, urlopen(req, timeout=timeout).read(), )

    def search(self, query, **etc):
        with self.thread_pool as ex:
            # perform every search using the thread pool executor
            logging.debug("Beginning search using thread pool for query {query}.".format(query=query))
            yield from ex.map(self.__do_request, self.build_qs(query, **etc))

    # NOTE: raw_html function is broken now that listings are JavaScript...
    def find_elements(self, html, raw_html=False):
        logging.debug("Parsing HTML...")
        soup = BeautifulSoup(html, 'html.parser')

        # Webpage uses a javascript data structure to hold ad info
        for script in soup.find_all('script'):
            if "listings: " in str(script):
                # reduce script to just json structure
                # Looks something like this right now:
                #  window.renderSearchSection({ listings: [{"id" . . .
                #  ...
                #  })
                # So we just need to grab stuff between outer parens
                list_json = (script.contents[0].split('(', 1)[-1]
                                               .rsplit(')', 1)[0])
                # Put double quotes around property name
                list_json = list_json.replace('listings: ', '"listings": ')
                # Remove unneeded and poorly formatted properties
                '''
                    displayType: 'grid',
                    userData: {"contactBehindLogin":true}
                '''
                # so just keep the first two lines, then fix struct ending
                list_json = "\n".join(list_json.split("\n")[:2])
                list_json = list_json.rstrip(',') + "}"
                # Turn the json into a dict and grab the list of listings
                listings = json.loads(list_json)['listings']
                logging.debug("Converted JSON listings into dictionary.")
                break

        # keys in each listing:
        #  'createTime', 'cellPhone', 'lat', 'modifyTime', 'sellerType',
        #  'marketType', 'favorited', 'state', 'city', 'source', 'lon',
        #  'description', 'pageviews', 'memberId', 'city_lower', 'subCategory',
        #  'photo', 'email', 'category', 'displayTime', 'price', 'zip',
        #  'homePhone', 'listingType', 'expireTime', 'title', 'id', 'name'
        logging.debug("Converting listing dictionary into Listing objects.")
        for ad_box in listings:
            if 'featured' in ad_box['listingType']:
                continue
            if 'price' not in ad_box:
                # Free items are missing the price
                ad_box['price'] = 0

            created = (datetime.strptime(ad_box['createTime'],
                                         "%Y-%m-%dT%H:%M:%SZ")
                       + self.time_offset)
            lifespan = str(created)
            link = urljoin(self.LIST_URL, str(ad_box['id']))
            yield Listing(ad_box['title'], ad_box['city'], ad_box['state'],
                          lifespan, ad_box['price'], link,
                          ad_box['description'])

    def build_qs(self, queries, **etc):
        logging.debug("Building query...")
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
                'priceTo': maxp
            }

            # apply defaults
            qs.update(self.URL_QS)

            # fill in any additional parameters
            # that were passed, but not explicitly handled
            for k, value in args.items():
                if k in KSL.QUERY_PARAM_KEYS:
                    qs.setdefault(k, value)

            # Remove None values
            qs = {k: v for k, v in qs.items() if v is not None}

            logging.debug("Using the following query params: {query}".format(query=qs))

            # encode
            qs = urlencode(qs)
            queryurl = self.SEARCH_URL + qs
            logging.debug("Generated the search URL: {url}".format(url=queryurl))
            yield (query, queryurl, )

    def listing(id):
        pass


def gather_report(query_result):
    logging.debug("Gathering report for {count} listings".format(count=len(query_result)))
    report = ""
    for result in query_result:
        report += ('{result.title} - ${result.price} - {result.age} : '
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
                print("** Search for %s **" % query)
            print(report)


if __name__ == '__main__':
    args = KslCliParser().parser.parse_args()

    # do it
    main(vars(args))
