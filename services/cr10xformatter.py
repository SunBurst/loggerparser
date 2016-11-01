#!/usr/bin/env
# -*- coding: utf-8 -*-

"""Module for formatting and exporting Campbell CR10X mixed-array datalogger files. """

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import logging.config
import time

from campbellsciparser import cr

from services import common
from services import utils

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
APP_CONFIG_PATH = os.path.join(BASE_DIR, 'cfg/cr10xformatter.yaml')
LOGGING_CONFIG_PATH = os.path.join(BASE_DIR, 'cfg/logging.yaml')

logging_conf = utils.load_config(LOGGING_CONFIG_PATH)
logging.config.dictConfig(logging_conf)
logger = logging.getLogger('cr10xformatter')


def convert_data_time_values(data, column_name, value_time_columns, time_zone,
                             time_format_args_library, to_utc):
    """Convert time values (data column).

    Parameters
    ----------
    data : DataSet
        Data set to convert.
    column_name: str or int
        Time column name (or index) to convert.
    value_time_columns : list of str or int
        Column(s) (names or indices) to use for time conversion.
    time_zone : str
        String representation of a valid pytz time zone. (See pytz docs
        for a list of valid time zones). The time zone refers to collected data's
        time zone, which defaults to UTC and is used for localization and time conversion.
    time_format_args_library : list of str
        List of the maximum expected string format columns sequence to match against
        when parsing time values.
    to_utc : bool
        If the data type to convert is 'time', convert to UTC.

    Returns
    -------
    DataSet
        Data time converted data set.

    """
    return cr.parse_time(
        data=data,
        time_zone=time_zone,
        time_format_args_library=time_format_args_library,
        time_parsed_column=column_name,
        time_columns=value_time_columns,
        replace_time_column=column_name,
        to_utc=to_utc)


def make_data_set_backup(data):
    """Returns a copy of the given data set.

    Parameters
    ----------
    data : DataSet
        Data set to backup.

    Returns
    -------
    DataSet
        Copy of given data set.

    """
    return cr.DataSet(
        [cr.Row([(name, value) for name, value in row.items()])
         for row in data]
    )


def make_export_data_set(data, columns_to_export):
    """Create an 'export' data set, i.e. a data set filtered by columns to export.

    Parameters
    ----------
    data : DataSet
        Data set to extract columns from.

    columns_to_export : list of str or int
        Columns to extract from source data set.

    Returns
    -------
    DataSet
        Data set ready to export.

    """
    data_to_export = cr.DataSet()
    for row in data:
        data_to_export.append(cr.Row(
            [(name, value) for name, value in row.items() if name in columns_to_export]
        ))

    return data_to_export


def restore_data_after_data_time_conversion(data, data_backup, converted_column_name):
    """Convenience for restoring time values that was removed for data time conversion.

    Parameters
    ----------
    data : DataSet
        Data time value converted data set.
    data_backup : DataSet
        Source data set.
    converted_column_name : str or int
        Column name (or index) that was converted.

    Returns
    -------
    DataSet
        Data time converted data set with its original time values restored.

    """
    data_converted = []

    for row in data:
        converted_values = cr.Row()
        for converted_name, converted_value in row.items():
            if converted_name == converted_column_name:
                converted_values[converted_column_name] = converted_value

                data_converted.append(converted_values)

    data_merged = [row for row in common.update_column_values_generator(
        data_old=data_backup,
        data_new=data_converted
    )]

    return data_merged


def convert_data_column_values(data, values_to_convert, time_zone, time_format_args_library, to_utc):
    """Converts certain column values.

    Parameters
    ----------
    data : DataSet
        data set to convert.
    values_to_convert : dict
        Columns to convert.
    time_zone : str
        String representation of a valid pytz time zone. (See pytz docs
        for a list of valid time zones). The time zone refers to collected data's
        time zone, which defaults to UTC and is used for localization and time conversion.
    time_format_args_library : list of str
        List of the maximum expected string format columns sequence to match against
        when parsing time values.
    to_utc : bool
        If the data type to convert is 'time', convert to UTC.

    Returns
    -------
    DataSet
        Column values converted data set.

    """
    data_converted = cr.DataSet()

    data_backup = make_data_set_backup(data)

    for column_name, convert_column_info in values_to_convert.items():
        value_type = convert_column_info.get('value_type')
        value_time_columns = convert_column_info.get('value_time_columns')

        if value_type == 'time':
            array_id_data_converted_values_all = convert_data_time_values(
                data=data,
                column_name=column_name,
                value_time_columns=value_time_columns,
                time_zone=time_zone,
                time_format_args_library=time_format_args_library,
                to_utc=to_utc
            )
        else:
            msg = "Only time conversion is supported in this version."
            raise common.UnsupportedValueConversionType(msg)

        data_converted = restore_data_after_data_time_conversion(
            data=array_id_data_converted_values_all,
            data_backup=data_backup,
            converted_column_name=column_name
        )

    return data_converted


def process_array_ids(site, location, data, time_zone, time_format_args_library,
                      output_dir, array_ids_info, file_ext):
    """Splits apart mixed array location files into subfiles based on each rows' array id.

    Parameters
    ----------
    site : str
        Site id.
    location : str
        Location id.
    data : dict of DataSet
        Mixed array data set, split by array ids.
    time_zone : str
        String representation of a valid pytz time zone. (See pytz docs
        for a list of valid time zones). The time zone refers to collected data's
        time zone, which defaults to UTC and is used for localization and time conversion.
    time_format_args_library : list of str
        List of the maximum expected string format columns sequence to match against
        when parsing time values.
    output_dir : str
        Output directory.
    array_ids_info : dict of dict
        File processing and exporting information.
    file_ext : str
        Output file extension.

    Raises
    ------
    UnsupportedValueConversionType: If an unsupported data value conversion type is given.

    """

    for array_id, array_id_info in array_ids_info.items():
        array_name = array_id_info.get('name', array_id)

        logger.info("Processing array: {array_name}".format(array_name=array_name))
        array_id_data = data.get(array_name)
        logger.info("{num} new rows".format(num=len(array_id_data)))

        if not array_id_data:
            logger.info("No work to be done for array: {array_name}".format(array_name=array_name))
            continue

        column_names = array_id_info.get('column_names')
        logger.debug("Column names : {column_names}".format(column_names=column_names))

        export_columns = array_id_info.get('export_columns')
        logger.debug(
            "Export columns: {export_columns}".format(export_columns=export_columns))

        include_time_zone = array_id_info.get('include_time_zone', False)
        logger.debug("Include time zone: {include_time_zone}".format(
            include_time_zone=include_time_zone))

        time_columns = array_id_info.get('time_columns')
        logger.debug("Time columns: {time_columns}".format(time_columns=time_columns))

        time_parsed_column_name = array_id_info.get('time_parsed_column_name', 'Timestamp')
        logger.debug("Time parsed column {time_parsed_column_name}".format(
            time_parsed_column_name=time_parsed_column_name))

        to_utc = array_id_info.get('to_utc', False)
        logger.debug("To UTC {to_utc}".format(to_utc=to_utc))

        column_values_to_convert = array_id_info.get('convert_data_column_values')
        logger.debug("Convert column_values: {column_values_to_convert}".format(
            column_values_to_convert=column_values_to_convert))

        array_id_file = array_name + file_ext
        logger.debug("Array id file: {array_id_file}".format(
            array_id_file=array_id_file))

        array_id_file_path = os.path.join(
            os.path.abspath(output_dir), site, location, array_id_file)
        logger.debug("Array id file path: {array_id_file_path}".format(
            array_id_file_path=array_id_file_path))

        array_id_mismatches_file = array_name + ' Mismatches' + file_ext
        logger.debug("Array id mismatched file: {array_id_mismatches_file}".format(
            array_id_mismatches_file=array_id_mismatches_file))

        array_id_mismatches_file_path = os.path.join(
            os.path.abspath(output_dir), site, location, array_id_mismatches_file)
        logger.debug(
            "Array id mismatched file path: {array_id_mismatches_file_path}".format(
                array_id_mismatches_file_path=array_id_mismatches_file_path))

        logger.info("Assigning column names")

        array_id_data_with_column_names, mismatches = cr.update_column_names(
            data=array_id_data,
            column_names=column_names,
            match_row_lengths=True,
            get_mismatched_row_lengths=True)

        logger.info("Number of matched row lengths: {matched}".format(
            matched=len(array_id_data_with_column_names)))
        logger.info("Number of mismatched row lengths: {mismatched}".format(
            mismatched=len(mismatches)))

        if column_values_to_convert:
            array_id_data_with_column_names = convert_data_column_values(
                data=array_id_data_with_column_names,
                values_to_convert=column_values_to_convert,
                time_zone=time_zone,
                time_format_args_library=time_format_args_library,
                to_utc=to_utc
            )

        array_id_data_time_converted = cr.parse_time(
            data=array_id_data_with_column_names,
            time_zone=time_zone,
            time_format_args_library=time_format_args_library,
            time_parsed_column=time_parsed_column_name,
            time_columns=time_columns,
            to_utc=to_utc)

        data_to_export = make_export_data_set(
            data=array_id_data_time_converted, columns_to_export=export_columns)

        cr.export_to_csv(
            data=data_to_export,
            outfile_path=array_id_file_path,
            export_header=True,
            include_time_zone=include_time_zone
        )

        if mismatches:
            cr.export_to_csv(data=mismatches, outfile_path=array_id_mismatches_file_path)


def process_location(cfg, output_dir, site, location, location_info, track=False):
    """Splits apart mixed array location files into subfiles based on each rows' array id.

    Parameters
    ----------
    cfg : dict
        Program's configuration file.
    output_dir : str
        Output directory.
    site : str
        Site id.
    location : str
        Location id.
    location_info : dict
        Location information including the location's array ids lookup table, source file
        path and last read line number.
    track: If true, update configuration file with the last read line number.

    Returns
    -------
        Updated configuration file.

    """
    logger.info("Processing location: {location}".format(location=location))

    logger.debug("Getting location configuration.")

    array_ids_info = location_info.get('array_ids', {})
    logger.debug(
        "Array ids info: {array_ids_info}".format(array_ids_info=array_ids_info))

    file_path = location_info.get('file_path')
    logger.debug("File path: {file_path}".format(file_path=file_path))

    line_num = location_info.get('line_num', 0)
    logger.debug("Line num: {line_num}".format(line_num=line_num))

    time_zone = location_info.get('time_zone')
    logger.debug("Time zone: {time_zone}".format(time_zone=time_zone))

    time_format_args_library = location_info.get('time_format_args_library')
    logger.debug("Time format args library: {time_format_args_library}".format(
        time_format_args_library=time_format_args_library))

    array_id_names = {
        array_id: array_id_info.get('name', array_id)
        for array_id, array_id_info in array_ids_info.items()
    }

    data = cr.read_array_ids_data(
        infile_path=file_path,
        first_line_num=line_num,
        fix_floats=True,
        array_id_names=array_id_names
    )

    num_of_new_rows = 0

    for array_id, array_id_data in data.items():
        num_of_new_rows += len(array_id_data)

    logger.info("Found {num} new rows".format(num=num_of_new_rows))
    if num_of_new_rows == 0:
        logger.info("No work to be done for location: {location}".format(location=location))
        return cfg

    file_ext = os.path.splitext(os.path.abspath(file_path))[1]  # Get file extension
    logger.debug("File ext: {file_ext}".format(file_ext=file_ext))

    process_array_ids(
        site=site,
        location=location,
        array_ids_data=data,
        time_zone=time_zone,
        time_format_args_library=time_format_args_library,
        output_dir=output_dir,
        array_ids_info=array_ids_info,
        file_ext=file_ext
    )

    if track:
        if num_of_new_rows > 0:
            new_line_num = line_num + num_of_new_rows
            logger.info("Updated up to line number {num}".format(num=new_line_num))
            cfg['sites'][site]['locations'][location]['line_num'] = new_line_num

    msg = "Done processing site {site}, location {location}"
    logger.info(msg.format(site=site, location=location))

    return cfg


def process_sites(cfg, args):
    """Unpacks data from the configuration file, calls the core function and updates line
        number information if tracking is enabled.

    Parameters
    ----------
    cfg : dict
        Program's configuration file.
    args : Namespace
        Arguments passed by the user. Includes site, location and tracking information.

    """
    try:
        output_dir = cfg['settings']['data_output_dir']
    except KeyError:
        output_dir = os.path.expanduser("~")
        msg = "No output directory set! "
        msg += "Files will be output to the user's default directory at {output_dir}"
        msg = msg.format(output_dir=output_dir)
        logger.info(msg)

    logger.debug("Output directory: {dir}".format(dir=output_dir))
    logger.debug("Getting configured sites.")
    sites = cfg['sites']
    configured_sites_msg = ', '.join("{site}".format(site=site) for site in sites)
    logger.debug("Configured sites: {sites}.".format(sites=configured_sites_msg))

    if args.track:
        logger.info("Tracking is enabled.")
    else:
        logger.info("Tracking is disabled.")

    if args.site:
        logger.info("Processing site: {site}".format(site=args.site))
        site_info = sites[args.site]
        logger.debug("Getting configured locations.")
        locations = site_info['locations']
        configured_locations_msg = ', '.join("{location}".format(
            location=location) for location in locations)
        logger.debug("Configured locations: {locations}.".format(
            locations=configured_locations_msg))
        if args.location:
            location_info = locations[args.location]
            cfg = process_location(
                cfg, output_dir, args.site, args.location, location_info, args.track)
        else:
            for location, location_info in locations.items():
                cfg = process_location(
                    cfg, output_dir, args.site, location, location_info, args.track)

        logger.info("Done processing site: {site}".format(site=args.site))
    else:
        for site, site_info in sites.items():
            logger.info("Processing site: {site}".format(site=site))
            locations = site_info['locations']
            configured_locations_msg = ', '.join("{location}".format(
                location=location) for location in locations)
            logger.debug("Configured locations: {locations}.".format(
                locations=configured_locations_msg))
            for location, location_info in locations.items():
                cfg = process_location(
                    cfg, output_dir, site, location, location_info, args.track)

            logger.info("Done processing site: {site}".format(site=args.site))

    if args.track:
        logger.info("Updating config file.")
        utils.save_config(APP_CONFIG_PATH, cfg)


def main():
    """Parses and validates arguments from the command line. """
    parser = argparse.ArgumentParser(
        prog='CR10XFormatter',
        description='Program for formatting and exporting Campbell CR10X mixed array datalogger files.'
    )
    parser.add_argument('-s', '--site', action='store', dest='site',
                        help='Site to process.')
    parser.add_argument('-l', '--location', action='store', dest='location',
                        help='Location to process.')
    parser.add_argument(
        '-t', '--track',
        help='Track file line number.',
        dest='track',
        action='store_true',
        default=False
    )

    args = parser.parse_args()
    logger.debug("Arguments passed by user")
    args_msg = ', '.join("{arg}: {value}".format(
        arg=arg, value=value) for (arg, value) in vars(args).items())

    logger.debug(args_msg)

    if args.location and not args.site:
        parser.error("--site and --location are required.")

    app_cfg = utils.load_config(APP_CONFIG_PATH)

    system_is_active = app_cfg['settings']['active']
    if not system_is_active:
        logger.info("System is not active.")
        return

    logger.info("System is active")
    logger.info("Initializing")

    start = time.time()
    process_sites(app_cfg, args)
    stop = time.time()
    elapsed = (stop - start)

    logger.info("Finished job in {elapsed} seconds".format(elapsed=elapsed))

if __name__ == '__main__':
    main()
    logger.info("Exiting.")
