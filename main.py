from pathlib import Path
import argparse
import json
import time
import sys
import traceback

import requests
import scrapy
import pandas as pd
from requests.exceptions import RequestException

from land_record_crud import LandRecordCRUD
from models import db_session


class FormFieldNotFoundException(Exception):
    def __init__(self, missing_fields: list):
        self.missing_fields = missing_fields
        message = f"Failed to extract essential fields: {', '.join(missing_fields)}."
        super().__init__(message)


def retry_on_exception(retries=3, delay=5, allowed_exceptions=(Exception,)):
    """
    Decorator to retry a function if an exception occurs.

    :param retries: Number of times to retry the function.
    :param delay: Delay in seconds between retries.
    :param allowed_exceptions: Tuple of exception classes to catch and retry on.
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            attempt = 0
            err = None
            while attempt < retries:
                try:
                    # time.sleep(2)
                    return func(*args, **kwargs)
                except allowed_exceptions as e:
                    attempt += 1
                    print(f"Error: {e}. Retrying {attempt}/{retries}...")
                    err = traceback.format_exc()
                    time.sleep(delay)
            # If all retries failed, print traceback and exit with the error message
            print(err)
            print("All retries failed. Here's the traceback:")
            sys.exit("Please try again later; something went wrong.")
        return wrapper
    return decorator


class JamabandiDataExtractor:
    """
    A class to extract land record data from the Jamabandi website.
    """

    # Default headers for requests
    headers = {
        'Host': 'jamabandi.nic.in',
        'user-agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0',
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/png,image/svg+xml,*/*;q=0.8',
        'accept-language': 'en-US,en;q=0.5',
        'upgrade-insecure-requests': '1',
        'sec-fetch-dest': 'document',
        'sec-fetch-mode': 'navigate',
        'sec-fetch-site': 'none',
        'sec-fetch-user': '?1',
        'priority': 'u=0, i',
    }

    # Base URI for Jamabandi
    jamabandi_uri = 'https://jamabandi.nic.in/land%20records/NakalRecord'
    
    def __init__(self) -> None:
        """
        Initializes the JamabandiDataExtractor with default settings.
        
        Sets up a requests session and initializes state variables to store form values.
        """
        self.req_session = requests.Session()  # Create a new session for requests
        self.viewstate = None                 # ViewState hidden field value (for ASP.NET pages)
        self.event_arg = None                 # Event argument hidden field value
        self.event_validation = None          # Event validation hidden field value
        self.viewstate_generator = None       # ViewState generator hidden field value
        self.request_timeout = 40

    @retry_on_exception(retries=3, delay=5, allowed_exceptions=(RequestException, Exception))
    def get_jamabandi_page(self) -> None:
        """
        Fetches the Jamabandi page and extracts form values for state management.
        
        Makes a GET request to the Jamabandi URI to retrieve the initial page content.
        Parses the page to extract hidden form fields used for subsequent POST requests.
        """
        response = self.req_session.get(self.jamabandi_uri, headers=self.headers, timeout=self.request_timeout)
        response.raise_for_status()  # Raise an HTTPError for bad responses (4xx and 5xx)

        # Create a Selector object from the response text to facilitate XPath queries
        selector = scrapy.Selector(text=response.text)

        # Extract hidden form field values
        self.viewstate = selector.xpath('//input[@name="__VIEWSTATE"]/@value').get()
        self.event_arg = selector.xpath('//input[@name="__EVENTARGUMENT"]/@value').get()
        self.event_validation = selector.xpath('//input[@name="__EVENTVALIDATION"]/@value').get()
        self.viewstate_generator = selector.xpath('//input[@name="__VIEWSTATEGENERATOR"]/@value').get()

        # Validate if essential fields were extracted
        if not self.viewstate or not self.viewstate_generator or not self.event_validation:
            print("Failed to extract essential form fields from the Jamabandi page.")
            raise FormFieldNotFoundException(['viewstate', 'event_validation', 'viewstate_generator'])


    @retry_on_exception(retries=3, delay=5, allowed_exceptions=(RequestException, Exception))
    def get_districts(self) -> dict:
        """
        Retrieves the list of districts from the Jamabandi page.
        
        Sends a POST request with the required form data to get the districts dropdown options.
        Extracts and returns a dictionary of district names and their corresponding IDs.
        
        Returns:
            dict: A dictionary where keys are district names and values are district IDs.
        """
        # Prepare data for the POST request to fetch district options
        data = {
            '__EVENTTARGET': 'ctl00$ContentPlaceHolder1$RdobtnKhasra',
            '__EVENTARGUMENT': '',
            '__LASTFOCUS': '',
            '__VIEWSTATE': self.viewstate,
            '__VIEWSTATEGENERATOR': self.viewstate_generator,
            '__SCROLLPOSITIONX': '0',
            '__SCROLLPOSITIONY': '0',
            '__VIEWSTATEENCRYPTED': '',
            '__EVENTVALIDATION': self.event_validation,
            'ctl00$ContentPlaceHolder1$a': 'RdobtnKhasra',
            'ctl00$ContentPlaceHolder1$ddldname': '-1',
        }

        districts = {}

        # Send POST request
        response = self.req_session.post(self.jamabandi_uri, headers=self.headers, 
                                        data=data, timeout=self.request_timeout)
        response.raise_for_status()  # Raise an HTTPError for bad responses (4xx and 5xx)

        # Create a Selector object from the response text to facilitate XPath queries
        selector = scrapy.Selector(text=response.text)

        # Update state variables with new values from the response
        viewstate = selector.xpath('//input[@name="__VIEWSTATE"]/@value').get()
        event_validation = selector.xpath('//input[@name="__EVENTVALIDATION"]/@value').get()

        # Validate if essential fields were extracted
        if not viewstate or not event_validation:
            print("Failed to extract essential form fields from the Jamabandi page.")
            raise FormFieldNotFoundException(['viewstate', 'event_validation'])
        
        self.viewstate = viewstate
        self.event_validation = event_validation
        
        # Extract district options from the response
        district_options = selector.xpath('//div[contains(./label/text(), "Select District")]/select/option[not(@selected)]')

        # Create a dictionary of districts
        districts = {district_option.xpath('./text()').get(): district_option.xpath(
            './@value').get() for district_option in district_options}
            
        if not districts:
            raise FormFieldNotFoundException(['districts'])
        return districts

    @retry_on_exception(retries=3, delay=5, allowed_exceptions=(RequestException, Exception))
    def get_sub_districts(self, district_id: str) -> dict:
        """
        Retrieves the list of sub-districts (Tehsil/Sub-Tehsil) for a given district.

        Sends a POST request with the district ID to fetch the sub-district dropdown options.
        Extracts and returns a dictionary of sub-district names and their corresponding IDs.

        Args:
            district_id (str): The ID of the district for which to fetch sub-districts.

        Returns:
            dict: A dictionary where keys are sub-district names and values are sub-district IDs.
        """
        # Prepare data for the POST request to fetch sub-district options
        data = {
            '__EVENTTARGET': 'ctl00$ContentPlaceHolder1$ddldname',
            '__EVENTARGUMENT': self.event_arg,
            '__LASTFOCUS': '',
            '__VIEWSTATE': self.viewstate,
            '__VIEWSTATEGENERATOR': self.viewstate_generator,
            '__SCROLLPOSITIONX': '0',
            '__SCROLLPOSITIONY': '0',
            '__VIEWSTATEENCRYPTED': '',
            '__EVENTVALIDATION': self.event_validation,
            'ctl00$ContentPlaceHolder1$a': 'RdobtnKhasra',
            'ctl00$ContentPlaceHolder1$ddldname': district_id,
        }

        # Send POST request
        response = self.req_session.post(self.jamabandi_uri, headers=self.headers, data=data)
        response.raise_for_status()

        # Create a Selector object from the response text
        seletor = scrapy.Selector(text=response.text)
        
        # Update state variables with new values from the response
        viewstate = seletor.xpath('//input[@name="__VIEWSTATE"]/@value').get()
        event_validation = seletor.xpath('//input[@name="__EVENTVALIDATION"]/@value').get()

        # Validate if essential fields were extracted
        if not viewstate or not event_validation:
            print("Failed to extract essential form fields from the Jamabandi page.")
            raise FormFieldNotFoundException(['viewstate', 'event_validation'])
        
        self.viewstate = viewstate
        self.event_validation = event_validation

        # Extract sub-district options from the response
        sub_district_options = seletor.xpath('//div[contains(./label/text(), "Select Tehsil/ Sub-Tehsil")]/select/option[not(@selected)]')
        
        # Create a dictionary of sub-districts
        sub_districts = {sub_district_option.xpath('./text()').get(): sub_district_option.xpath(
            './@value').get() for sub_district_option in sub_district_options}

        if not sub_districts:
            raise FormFieldNotFoundException(['sub-districts'])
        return sub_districts

    @retry_on_exception(retries=3, delay=5, allowed_exceptions=(RequestException, Exception))
    def get_villeges(self, district_id: str, sub_district_id: str) -> dict:
        """
        Retrieves the list of villages for a given district and sub-district.

        Sends a POST request with the district and sub-district IDs to fetch the village dropdown options.
        Extracts and returns a dictionary of village names and their corresponding IDs.

        Args:
            district_id (str): The ID of the district.
            sub_district_id (str): The ID of the sub-district.

        Returns:
            dict: A dictionary where keys are village names and values are village IDs.
        """
        # Prepare data for the POST request to fetch village options
        data = {
            '__EVENTTARGET': 'ctl00$ContentPlaceHolder1$ddltname',
            '__EVENTARGUMENT': self.event_arg,
            '__LASTFOCUS': '',
            '__VIEWSTATE': self.viewstate,
            '__VIEWSTATEGENERATOR': self.viewstate_generator,
            '__SCROLLPOSITIONX': '0',
            '__SCROLLPOSITIONY': '0',
            '__VIEWSTATEENCRYPTED': '',
            '__EVENTVALIDATION': self.event_validation,
            'ctl00$ContentPlaceHolder1$a': 'RdobtnKhasra',
            'ctl00$ContentPlaceHolder1$ddldname': district_id,
            'ctl00$ContentPlaceHolder1$ddltname': sub_district_id,
        }

        # Send POST request
        response = self.req_session.post(self.jamabandi_uri, headers=self.headers, data=data)
        response.raise_for_status()

        # Create a Selector object from the response text
        seletor = scrapy.Selector(text=response.text)
        
        # Update state variables with new values from the response
        viewstate = seletor.xpath('//input[@name="__VIEWSTATE"]/@value').get()
        event_validation = seletor.xpath('//input[@name="__EVENTVALIDATION"]/@value').get()

        # Validate if essential fields were extracted
        if not viewstate or not event_validation:
            print("Failed to extract essential form fields from the Jamabandi page.")
            raise FormFieldNotFoundException(['viewstate', 'event_validation'])
        
        self.viewstate = viewstate
        self.event_validation = event_validation

        # Extract village options from the response
        village_options = seletor.xpath('//div[contains(./label/text(), "Select Village")]/select/option[not(@selected)]')
        
        # Create a dictionary of villages
        villages = {village_option.xpath('./text()').get(): village_option.xpath(
            './@value').get() for village_option in village_options}
        
        if not villages:
            raise FormFieldNotFoundException(['villeges'])
        return villages

    @retry_on_exception(retries=3, delay=5, allowed_exceptions=(RequestException, Exception))
    def get_years(self, district_id: str, sub_district_id: str, villege_id: str) -> list:
        """
        Retrieves the list of Jamabandi years for a given district, sub-district, and village.

        Sends a POST request with the district, sub-district, and village IDs to fetch the years dropdown options.
        Extracts and returns a list of available years.

        Args:
            district_id (str): The ID of the district.
            sub_district_id (str): The ID of the sub-district.
            villege_id (str): The ID of the village.

        Returns:
            list: A list of available Jamabandi years.
        """
        # Prepare data for the POST request to fetch years options
        data = {
            '__EVENTTARGET': 'ctl00$ContentPlaceHolder1$ddlvname',
            '__EVENTARGUMENT': self.event_arg,
            '__LASTFOCUS': '',
            '__VIEWSTATE': self.viewstate,
            '__VIEWSTATEGENERATOR': self.viewstate_generator,
            '__SCROLLPOSITIONX': '0',
            '__SCROLLPOSITIONY': '0',
            '__VIEWSTATEENCRYPTED': '',
            '__EVENTVALIDATION': self.event_validation,
            'ctl00$ContentPlaceHolder1$a': 'RdobtnKhasra',
            'ctl00$ContentPlaceHolder1$ddldname': district_id,
            'ctl00$ContentPlaceHolder1$ddltname': sub_district_id,
            'ctl00$ContentPlaceHolder1$ddlvname': villege_id,
        }

        # Send POST request
        response = self.req_session.post(self.jamabandi_uri, headers=self.headers, data=data)
        response.raise_for_status()

        # Create a Selector object from the response text
        seletor = scrapy.Selector(text=response.text)
        
        # Update state variables with new values from the response
        viewstate = seletor.xpath('//input[@name="__VIEWSTATE"]/@value').get()
        event_validation = seletor.xpath('//input[@name="__EVENTVALIDATION"]/@value').get()

        # Validate if essential fields were extracted
        if not viewstate or not event_validation:
            print("Failed to extract essential form fields from the Jamabandi page.")
            raise FormFieldNotFoundException(['viewstate', 'event_validation'])
        
        self.viewstate = viewstate
        self.event_validation = event_validation

        # Extract years options from the response
        years = seletor.xpath('//div[contains(./label/text(), "Jamabandi Year")]/select/option[not(@selected)]/@value').getall()

        if not years:
            raise FormFieldNotFoundException(['years'])
        return years

    @retry_on_exception(retries=3, delay=5, allowed_exceptions=(RequestException, Exception))
    def get_khasras(self, district_id: str, sub_district_id: str, villege_id: str, year: str) -> dict:
        """
        Retrieves the list of Khasra numbers for a given district, sub-district, village, and year.

        Sends a POST request with the district, sub-district, village IDs, and year to fetch the Khasra dropdown options.
        Extracts and returns a dictionary of Khasra numbers and their corresponding IDs.

        Args:
            district_id (str): The ID of the district.
            sub_district_id (str): The ID of the sub-district.
            villege_id (str): The ID of the village.
            year (str): The Jamabandi year.

        Returns:
            dict: A dictionary where keys are Khasra numbers and values are Khasra IDs.
        """
        # Prepare data for the POST request to fetch Khasra options
        data = {
            '__EVENTTARGET': 'ctl00$ContentPlaceHolder1$ddlPeriod',
            '__EVENTARGUMENT': self.event_arg,
            '__LASTFOCUS': '',
            '__VIEWSTATE': self.viewstate,
            '__VIEWSTATEGENERATOR': self.viewstate_generator,
            '__SCROLLPOSITIONX': '0',
            '__SCROLLPOSITIONY': '0',
            '__VIEWSTATEENCRYPTED': '',
            '__EVENTVALIDATION': self.event_validation,
            'ctl00$ContentPlaceHolder1$a': 'RdobtnKhasra',
            'ctl00$ContentPlaceHolder1$ddldname': district_id,
            'ctl00$ContentPlaceHolder1$ddltname': sub_district_id,
            'ctl00$ContentPlaceHolder1$ddlvname': villege_id,
            'ctl00$ContentPlaceHolder1$ddlPeriod': year,
        }
        khasras = {}
        # Send POST request
        response = self.req_session.post(self.jamabandi_uri, headers=self.headers, data=data)
        response.raise_for_status()

        # Create a Selector object from the response text
        seletor = scrapy.Selector(text=response.text)
        
        # Update state variables with new values from the response
        viewstate = seletor.xpath('//input[@name="__VIEWSTATE"]/@value').get()
        event_validation = seletor.xpath('//input[@name="__EVENTVALIDATION"]/@value').get()

        # Validate if essential fields were extracted
        if not viewstate or not event_validation:
            print("Failed to extract essential form fields from the Jamabandi page.")
            raise FormFieldNotFoundException(['viewstate', 'event_validation'])
        
        self.viewstate = viewstate
        self.event_validation = event_validation

        # Extract Khasra options from the response
        khasra_options = seletor.xpath('//div[contains(./label/text(), "Khasra")]/select/option[not(@selected)]')
        
        # Create a dictionary of Khasras
        khasras = {khasra_option.xpath('./text()').get(): khasra_option.xpath(
            './@value').get() for khasra_option in khasra_options}
        
        if not khasras:
            raise FormFieldNotFoundException(['khasras'])
        return khasras

    @retry_on_exception(retries=3, delay=5, allowed_exceptions=(RequestException, Exception))
    def get_nakals(self, district_id: str, sub_district_id: str, villege_id: str, year: str, khasra_id: str) -> tuple:
        """
        Retrieves the list of Nakals (documents) for a given district, sub-district, village, year, and Khasra number.

        Sends a POST request with the district, sub-district, village IDs, year, and Khasra ID to fetch the Nakal options.
        Extracts and returns a list of Nakal IDs.

        Args:
            district_id (str): The ID of the district.
            sub_district_id (str): The ID of the sub-district.
            villege_id (str): The ID of the village.
            year (str): The Jamabandi year.
            khasra_id (str): The Khasra ID.

        Returns:
            list: A list of Nakal IDs.
        """
        # Prepare data for the POST request to fetch Nakal options
        data = {
            '__EVENTTARGET': 'ctl00$ContentPlaceHolder1$ddlkhasra',
            '__EVENTARGUMENT': self.event_arg,
            '__LASTFOCUS': '',
            '__VIEWSTATE': self.viewstate,
            '__VIEWSTATEGENERATOR': self.viewstate_generator,
            '__SCROLLPOSITIONX': '0',
            '__SCROLLPOSITIONY': '0',
            '__VIEWSTATEENCRYPTED': '',
            '__EVENTVALIDATION': self.event_validation,
            'ctl00$ContentPlaceHolder1$a': 'RdobtnKhasra',
            'ctl00$ContentPlaceHolder1$ddldname': district_id,
            'ctl00$ContentPlaceHolder1$ddltname': sub_district_id,
            'ctl00$ContentPlaceHolder1$ddlvname': villege_id,
            'ctl00$ContentPlaceHolder1$ddlPeriod': year,
            'ctl00$ContentPlaceHolder1$ddlkhasra': khasra_id,
        }

        # Send POST request
        response = self.req_session.post(self.jamabandi_uri, headers=self.headers, data=data)
        response.raise_for_status()

        # Create a Selector object from the response text
        seletor = scrapy.Selector(text=response.text)
        
        # Update state variables with new values from the response
        viewstate = seletor.xpath('//input[@name="__VIEWSTATE"]/@value').get()
        event_validation = seletor.xpath('//input[@name="__EVENTVALIDATION"]/@value').get()

        # Validate if essential fields were extracted
        if not viewstate or not event_validation:
            print("Failed to extract essential form fields from the Jamabandi page.")
            raise FormFieldNotFoundException(['viewstate', 'event_validation'])
        
        self.viewstate = viewstate
        self.event_validation = event_validation

        # Extract Nakal options from the response
        nakal_table_rows = seletor.xpath('//table[contains(@id, "GridView")]//tr[./td]')
        
        # Create a list of Nakal IDs and other related details
        nakals = []
        nakal_detail = {'khewat_no': '', 'khatoni_no': ''}
        for nakal_table_row in nakal_table_rows:
            nakal_id = nakal_table_row.xpath('./td/a/@href').get()
            nakal_id = 'Select$' + nakal_id.split('$')[-1].replace("')", "")
            nakals.append(nakal_id)

            khewat_no = nakal_table_row.xpath('./td[2]/text()').get()
            khatoni_no = nakal_table_row.xpath('./td[3]/text()').get()
            nakal_detail['khatoni_no'] = khatoni_no
            nakal_detail['khewat_no'] = khewat_no
        
        if not nakals or not nakal_detail:
            raise FormFieldNotFoundException(['nakals', 'nakal_detail'])
        return nakals, nakal_detail

    @retry_on_exception(retries=3, delay=5, allowed_exceptions=(RequestException, Exception))
    def select_nakals(self, district_id: str, sub_district_id: str, villege_id: str, year: str, khasra_id: str, nakal_id: str):
        """
        Selects a specific Nakal (document) for a given district, sub-district, village, year, and Khasra number.

        Sends a POST request to select a Nakal based on the provided IDs and updates the state with new values from the response.

        Args:
            district_id (str): The ID of the district.
            sub_district_id (str): The ID of the sub-district.
            villege_id (str): The ID of the village.
            year (str): The Jamabandi year.
            khasra_id (str): The Khasra ID.
            nakal_id (str): The Nakal ID to select.
        """
        # Prepare data for the POST request to select Nakal
        data = {
            '__EVENTTARGET': 'ctl00$ContentPlaceHolder1$GridView1',
            '__EVENTARGUMENT': nakal_id,
            '__LASTFOCUS': '',
            '__VIEWSTATE': self.viewstate,
            '__VIEWSTATEGENERATOR': self.viewstate_generator,
            '__SCROLLPOSITIONX': '0',
            '__SCROLLPOSITIONY': '0',
            '__VIEWSTATEENCRYPTED': '',
            '__EVENTVALIDATION': self.event_validation,
            'ctl00$ContentPlaceHolder1$a': 'RdobtnKhasra',
            'ctl00$ContentPlaceHolder1$ddldname': district_id,
            'ctl00$ContentPlaceHolder1$ddltname': sub_district_id,
            'ctl00$ContentPlaceHolder1$ddlvname': villege_id,
            'ctl00$ContentPlaceHolder1$ddlPeriod': year,
            'ctl00$ContentPlaceHolder1$ddlkhasra': khasra_id,
        }

        # Send POST request
        response = self.req_session.post(self.jamabandi_uri, headers=self.headers, data=data)
        response.raise_for_status()

        # Create a Selector object from the response text
        seletor = scrapy.Selector(text=response.text)
        
        # Update state variables with new values from the response
        viewstate = seletor.xpath('//input[@name="__VIEWSTATE"]/@value').get()
        event_validation = seletor.xpath('//input[@name="__EVENTVALIDATION"]/@value').get()

        # Validate if essential fields were extracted
        if not viewstate or not event_validation:
            print("Failed to extract essential form fields from the Jamabandi page.")
            raise FormFieldNotFoundException(['viewstate', 'event_validation'])
        
        self.viewstate = viewstate
        self.event_validation = event_validation

    @retry_on_exception(retries=3, delay=5, allowed_exceptions=(RequestException, Exception))
    def get_nakal_html(self, destination_path: Path|None=None) -> str:
        """
        Retrieves the HTML content of a Nakal document and saves it to a specified file.

        Sends a GET request to fetch the Nakal HTML content, writes the content to the given file path, and returns the HTML text.

        Args:
            destination_path (Path): The path where the Nakal HTML content will be saved.

        Returns:
            str: The HTML content of the Nakal document.
        """
        
        headers = {
            'Host': 'jamabandi.nic.in',
            'user-agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0',
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/png,image/svg+xml,*/*;q=0.8',
            'accept-language': 'en-US,en;q=0.5',
            'referer': 'https://jamabandi.nic.in/land%20records/NakalRecord',
            'upgrade-insecure-requests': '1',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'same-origin',
            'priority': 'u=0, i',
            'te': 'trailers'
        }

        # Send GET request to retrieve Nakal HTML content
        response = self.req_session.get('https://jamabandi.nic.in/land%20records/Nakal_khewat', headers=headers)
        response.raise_for_status()
        
        if destination_path:
            destination_path.write_text(response.text)
        return response.text


def extract_data(inp_district_name: str, inp_sub_district_name: str, 
                 inp_villege_name: str, inp_khasra_no: str, 
                 destination_path: Path|None=None) -> dict:
    """
    Extrats Land data and return output
    """
    jamabandi_obj = JamabandiDataExtractor()
    print("Fetching jamabandi page.")
    jamabandi_obj.get_jamabandi_page()

    print("Getting districts.")
    districts = jamabandi_obj.get_districts()
    # print(districts)
    if inp_district_name not in districts:
        return f'District name:{inp_district_name} not found!'
    district_id = districts[inp_district_name]
    
    print("Getting sub-districts.")
    sub_districts = jamabandi_obj.get_sub_districts(district_id=district_id)
    # print(sub_districts)
    if inp_sub_district_name not in sub_districts:
        return f'sub-district/tehsil name:{inp_sub_district_name} not found!'
    sub_district_id = sub_districts[inp_sub_district_name]

    print("Getting villeges.")
    villeges = jamabandi_obj.get_villeges(district_id=district_id, sub_district_id=sub_district_id)
    # print(villeges)
    if inp_villege_name not in villeges:
        return f'Villege name:{inp_villege_name} not found!'
    villege_id = villeges[inp_villege_name]

    print("Getting years.")
    years = jamabandi_obj.get_years(
        district_id=district_id, 
        sub_district_id=sub_district_id, 
        villege_id=villege_id
        )
    # print(years)
    if not years:
        return f'Year is empty!'

    print("Getting khasras.")
    khasras = jamabandi_obj.get_khasras(
        district_id=district_id, 
        sub_district_id=sub_district_id, 
        villege_id=villege_id, year=years[0], 
        )
    # print(khasras)
    if inp_khasra_no not in khasras:
        return f'Khasra number:{inp_khasra_no} not found!'
    khasra_id = khasras[inp_khasra_no]

    print("Getting nakals.")
    nakals, nakal_detail = jamabandi_obj.get_nakals(
        district_id=district_id, 
        sub_district_id=sub_district_id, 
        villege_id=villege_id, 
        year=years[0], khasra_id=khasra_id
        )
    # print(nakals)
    if not nakals:
        return f'Nakal is empty!'

    print("Selecing nakal.")
    jamabandi_obj.select_nakals(
        district_id=district_id, 
        sub_district_id=sub_district_id, 
        villege_id=villege_id, 
        year=years[0], khasra_id=khasra_id, 
        nakal_id=nakals[0]
        )
    
    print("Getting nakal html.")
    nakal_html_response = jamabandi_obj.get_nakal_html(destination_path=destination_path)

    nakal_selector = scrapy.Selector(text=nakal_html_response)
    nakal_villege = nakal_selector.xpath('//span[@id="lblvill"]/text()').get()
    nakal_hadbast = nakal_selector.xpath('//span[@id="lblhad"]/text()').get()
    nakal_tehsil = nakal_selector.xpath('//span[@id="lblteh"]/text()').get()
    nakal_district = nakal_selector.xpath('//span[@id="lbldis"]/text()').get()
    nakal_year = nakal_selector.xpath('//span[@id="lblyer"]/text()').get()
    
    output = {
        'district_name': inp_district_name,
        'district_code': district_id,
        'tehsil_name': inp_sub_district_name,
        'tehsil_code': sub_district_id,
        'villege_name': inp_villege_name,
        'villege_code': villege_id,
        'jamabandi_year': years[0],
        'khewat_no': nakal_detail['khewat_no'],
        'khatoni_no': nakal_detail['khatoni_no'],
        'khasra_code': khasra_id,
        'khasra_no': inp_khasra_no,
        'inner_details': {
            'villege': nakal_villege,
            'hadbast_no': nakal_hadbast,
            'tehsil': nakal_tehsil,
            'district': nakal_district,
            'year': nakal_year
        }
    }
    return output


def get_command_line_arg():
    """
    Parse and return command-line arguments for searching LandRecord records.

    The function takes the following command-line arguments:
    
    --district_name (str): Name of the district (required).
    --sub_district_name (str): Name of the sub-district (required).
    --village_name (str): Name of the village (required).
    --khasra_no (str): The Khasra number (required).
    --force_refresh (flag): Optional flag to force refresh existing data. If this 
                            flag is provided, it will set the value to True; 
                            otherwise, it defaults to False.

    Returns:
        argparse.Namespace: An object containing all parsed arguments.
    
    Example usage:
        python main.py --district_name 'नुह' --sub_district_name 'नगीना' --village_name 'F. pur dehar' --khasra_no '1//17' --force_refresh
                        or
        python main.py --district_name 'नुह' --sub_district_name 'नगीना' --village_name 'F. pur dehar' --khasra_no '1//17'
    """
    parser = argparse.ArgumentParser(description='Process some input parameters.')
    
    # Define the arguments
    parser.add_argument('--district_name', type=str, required=True, help='District name')
    parser.add_argument('--sub_district_name', type=str, required=True, help='Sub-district name')
    parser.add_argument('--village_name', type=str, required=True, help='Village name')
    parser.add_argument('--khasra_no', type=str, required=True, help='Khasra number')
    parser.add_argument('--force_refresh', action='store_true', help='Set to True if force refresh is enabled, to refresh existing data.')

    # Parse the arguments
    args = parser.parse_args()
    
    # Access the arguments
    print('>>>>>>>>>>>>>>>>>>>>> Inserted Inputs <<<<<<<<<<<<<<<<<<<<<')
    print(f'District Name: {args.district_name}')
    print(f'Sub-district Name: {args.sub_district_name}')
    print(f'Village Name: {args.village_name}')
    print(f'Khasra Number: {args.khasra_no}')
    print(f'Force Refresh: {args.force_refresh}')
    return args

if __name__ == '__main__':
    # Setting path for html file
    path = Path('nakal_html_data')
    path.mkdir(exist_ok=True, parents=True)
        
    # Taking information from commandline
    args = get_command_line_arg()
    
    inp_district_name = args.district_name
    inp_sub_district_name = args.sub_district_name
    inp_villege_name = args.village_name
    inp_khasra_no = args.khasra_no  
    force_refresh = args.force_refresh

    # Setting filename for nakal table data
    html_path = path.joinpath(f"{inp_district_name}_{inp_sub_district_name}_{inp_villege_name}_{inp_khasra_no.replace('/', '-')}.html")

    
    # Getting data from db
    nakal_data = LandRecordCRUD(db_session).search_records_by_input_data(
        district_name=inp_district_name, tehsil_name=inp_sub_district_name,
        villege_name=inp_villege_name, khasra_no=inp_khasra_no)

    # Scraping data if data not in db or force_refresh is True
    if not nakal_data or force_refresh:
        print('>>>>>>>>>>>>>>>>>>>>>>>>> Data extraction started... <<<<<<<<<<<<<<<<<<')
        nakal_data = extract_data(
            inp_district_name=inp_district_name, inp_sub_district_name=inp_sub_district_name,
            inp_villege_name=inp_villege_name, inp_khasra_no=inp_khasra_no, destination_path=html_path
            )

        if isinstance(nakal_data, dict):
            # Saving the output
            data = {
                'district_name': nakal_data['district_name'],
                'district_code': nakal_data['district_code'],
                'tehsil_name': nakal_data['tehsil_name'],
                'tehsil_code': nakal_data['tehsil_code'],
                'villege_name': nakal_data['villege_name'],
                'villege_code': nakal_data['villege_code'],
                'jamabandi_year': nakal_data['jamabandi_year'],
                'khewat_no': nakal_data['khewat_no'],
                'khatoni_no': nakal_data['khatoni_no'],
                'khasra_code': nakal_data['khasra_code'],
                'khasra_no': nakal_data['khasra_no'],
                'nakal_villege': nakal_data['inner_details']['villege'],
                'nakal_hadbast': nakal_data['inner_details']['hadbast_no'],
                'nakal_tehsil': nakal_data['inner_details']['tehsil'],
                'nakal_district': nakal_data['inner_details']['district'],
                'nakal_year': nakal_data['inner_details']['year']
            }
            nakal_data = LandRecordCRUD(db_session).create_record_by_checking_record(
                district_name=inp_district_name, tehsil_name=inp_sub_district_name,
                villege_name=inp_villege_name, khasra_no=inp_khasra_no, data=data,
                force_refresh=force_refresh)

    print("#"*60)
    print(nakal_data)
