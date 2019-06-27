import os
import logging
import re
import zipfile
import csv
from collections import OrderedDict
from tempfile import gettempdir

import pandas as pd
import json

from google.cloud import storage

logger = logging.getLogger(__name__)


def get_label(key, value):
    """
    A long camelCased label to a readable sentence
    :param key:
    :return:
    """
    label = re.split('(?=[A-Z])', key)
    return ''.join(word + ' ' for word in label).capitalize()


def flatten_dict(value):
    """
    Flattens a dictionary object with (nested) list values. For example:
    a_registration:  another_list_registration: {
                    _tt667dsfs: [ x: { y: fs56df64sd3} ]
                    }

    => { a_registration.another_list_registration._tt667dsfs.x.y: 'fs56df64sd3' }
    :param value:
    :return:
    """
    flat = dict()
    for key, value in value.items():
        if isinstance(value, list):
            torn = dict()
            for index, x in enumerate(value):
                torn[f"items__{index}"] = pd.io.json.json_normalize(
                    x, sep="."
                ).to_dict(orient="records")[0]
                flat[key] = torn
        else:
            flat[key] = value
    return flat


def create_csv_file(surveys):
    """
    Creates the csv file that gets downloaded exclusively data on request.
    And flatten sub question to a 2 dimensional data representation
    ** for example:
    locationSearch: {
        mast: 'x3srrR'
        typea: 'A type'
        another: [ anotherList: {
                    _tt667dsfs: fs56df64sd3}
                    ]
        }
    => locationSearch.mast: 'x3srrR' ...
    => locationSearch.another.anotherList._tt667dsfs: 'fs56df64sd3' ...
    :param surveys:
    :return:
    """
    list_of_registrations = []
    for k, v in surveys.items():
        data = dict()
        for key, value in v["data"].items():
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        data[key] = pd.DataFrame(value).to_dict(orient="records")
                    else:
                        data[key] = ' | '.join(value)
            elif isinstance(value, dict):
                data[key] = flatten_dict(value)
            else:
                data[key] = value
        list_of_registrations.append(data)

    df = pd.io.json.json_normalize(list_of_registrations, sep=".")
    return df.to_csv()


def flatten_dict_or_create_subforms(value, reference, survey, list_of_subforms):
    """
    Flattens a dictionary object OR creates a subform with (nested) list values. For example:
    a_registration:  another_list_registration: {
                    _tt667dsfs: [ x: { y: fs56df64sd3} ]
                    }

    => This in a separate CSV { a_registration.another_list_registration._tt667dsfs.x.y: 'fs56df64sd3' }
    :param reference:
    :param value:
    :return:
    """
    flat = dict()
    for key, value in value.items():
        if isinstance(value, list):
            torn = OrderedDict()
            for index, x in enumerate(value):
                torn[f"items__{index}"] = pd.io.json.json_normalize(x, sep=".").to_dict(
                    orient="records"
                )[0]

            field_names = [list(torn[name].keys()) for name in list(torn.keys())]
            fields = ['serialNumber', *field_names[0]]

            subformsfile = open(f"{gettempdir()}/{reference}.csv", "a") if reference in list_of_subforms else \
                                                         open(f"{gettempdir()}/{reference}.csv", "w")
            writer = csv.DictWriter(subformsfile, fieldnames=fields)

            if reference not in list_of_subforms:
                writer.writeheader()
                list_of_subforms.append(reference)

            # TODO => Hij gaat hier 6 keer doorheen - ik heb niet genoed tijd gehad om dit te lossen
            for item in torn:
                ordered = OrderedDict(torn[item])
                ordered.update({'serialNumber': survey})
                writer.writerow(ordered)
            subformsfile.close()
        else:
            flat[key] = value
    return flat


def create_zip_file(surveys):
    """
    Creates the zip file that gets downloaded exclusively data on request.
    And flatten sub question to a 2 dimensional data representation
    ** for example:
    locationSearch: {
        mast: 'x3srrR'
        typea: 'A type'
        another: [ anotherList: {
                    _tt667dsfs: fs56df64sd3}
                    ]
        }
    => locationSearch.mast: 'x3srrR' ...
    => locationSearch.another.anotherList._tt667dsfs: 'fs56df64sd3' ...
    :param surveys:
    :return:
    """
    surveys_zip_location = f"{gettempdir()}/surveys.zip"
    surveys_zip = zipfile.ZipFile(surveys_zip_location, "w")
    list_of_registrations = []
    list_of_subforms = []
    for k, v in surveys.items():
        data = {'serialNumber': k}
        for key, value in v["data"].items():
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        data[key] = pd.DataFrame(value).to_dict(orient="records")
                    else:
                        data[key] = ' | '.join(value)
            elif isinstance(value, dict):
                data[key] = flatten_dict_or_create_subforms(value, key, k, list_of_subforms)
            else:
                data[key] = value
        list_of_registrations.append(data)

    df = pd.io.json.json_normalize(list_of_registrations, sep=".")
    df.to_csv(f"{gettempdir()}/surveys_main.csv", index=None)

    surveys_zip.write(f"{gettempdir()}/surveys_main.csv", 'surveys_main.csv')
    for subform_name in list_of_subforms:
        surveys_zip.write(f"{gettempdir()}/{subform_name}.csv", f"{subform_name}.csv")
    surveys_zip.close()

    return surveys_zip_location


def get_batch_registrations(bucket_name, prefix=None):
    """
        lists all the surveys in the bucket
        - Using the a stringgetter() - batch them into a single dict file
    """
    storage_client = storage.Client(
        os.environ.get("PROJECT", "Specified environment variable is not set.")
    )

    bucket = storage_client.get_bucket(bucket_name)

    latest = list(bucket.list_blobs(prefix=f'source/{prefix}/folders'))[-1].download_as_string() if prefix == 'surveys' else\
        list(bucket.list_blobs(prefix=f'source/registrations/{prefix}'))[-1].download_as_string()
    logger.info("Downloaded Survey String", latest)
    return json.loads(latest)
