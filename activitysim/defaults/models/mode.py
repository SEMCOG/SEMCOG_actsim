# ActivitySim
# See full license in LICENSE.txt.

import os
import logging

import orca
import pandas as pd
import yaml

from activitysim import activitysim as asim
from activitysim import tracing

from activitysim import skim as askim
from .util.mode import _mode_choice_spec

logger = logging.getLogger(__name__)


"""
Mode choice is run for all tours to determine the transportation mode that
will be used for the tour
"""


@orca.injectable()
def tour_mode_choice_settings(configs_dir):
    with open(os.path.join(configs_dir,
                           "configs",
                           "tour_mode_choice.yaml")) as f:
        return yaml.load(f)


@orca.injectable()
def tour_mode_choice_spec_df(configs_dir):
    with open(os.path.join(configs_dir,
                           "configs",
                           "tour_mode_choice.csv")) as f:
        return asim.read_model_spec(f)


@orca.injectable()
def tour_mode_choice_coeffs(configs_dir):
    with open(os.path.join(configs_dir,
                           "configs",
                           "tour_mode_choice_coeffs.csv")) as f:
        return pd.read_csv(f, index_col='Expression')


@orca.injectable()
def tour_mode_choice_spec(tour_mode_choice_spec_df,
                          tour_mode_choice_coeffs,
                          tour_mode_choice_settings):
    return _mode_choice_spec(tour_mode_choice_spec_df,
                             tour_mode_choice_coeffs,
                             tour_mode_choice_settings)


@orca.injectable()
def trip_mode_choice_settings(configs_dir):
    with open(os.path.join(configs_dir,
                           "configs",
                           "trip_mode_choice.yaml")) as f:
        return yaml.load(f)


@orca.injectable()
def trip_mode_choice_spec_df(configs_dir):
    with open(os.path.join(configs_dir,
                           "configs",
                           "trip_mode_choice.csv")) as f:
        return asim.read_model_spec(f)


@orca.injectable()
def trip_mode_choice_coeffs(configs_dir):
    with open(os.path.join(configs_dir,
                           "configs",
                           "trip_mode_choice_coeffs.csv")) as f:
        return pd.read_csv(f, index_col='Expression')


@orca.injectable()
def trip_mode_choice_spec(trip_mode_choice_spec_df,
                          trip_mode_choice_coeffs,
                          trip_mode_choice_settings):
    return _mode_choice_spec(trip_mode_choice_spec_df,
                             trip_mode_choice_coeffs,
                             trip_mode_choice_settings)


def _mode_choice_simulate(tours,
                          skims,
                          stack,
                          orig_key,
                          dest_key,
                          spec,
                          additional_constants,
                          omx=None):
    """
    This is a utility to run a mode choice model for each segment (usually
    segments are trip purposes).  Pass in the tours that need a mode,
    the Skim object, the spec to evaluate with, and any additional expressions
    you want to use in the evaluation of variables.
    """

    # FIXME - log
    # print "Skims3D %s skim_key2 values = %s" % ('in_period', tours['in_period'].unique())
    # print "Skims3D %s skim_key2 values = %s" % ('out_period', tours['out_period'].unique())

    # FIXME - check that periods are in time_periods?

    in_skims = askim.Skims3D(stack=stack,
                             left_key=orig_key, right_key=dest_key,
                             skim_key="in_period",
                             offset=-1)
    out_skims = askim.Skims3D(stack=stack,
                              left_key=dest_key, right_key=orig_key,
                              skim_key="out_period",
                              offset=-1)

    if omx is not None:
        in_skims.set_omx(omx)
        out_skims.set_omx(omx)

    skims.set_keys(orig_key, dest_key)

    locals_d = {
        "in_skims": in_skims,
        "out_skims": out_skims,
        "skims": skims
    }
    locals_d.update(additional_constants)

    choices, _ = asim.simple_simulate(tours,
                                      spec,
                                      skims=[in_skims, out_skims, skims],
                                      locals_d=locals_d)

    alts = spec.columns
    choices = choices.map(dict(zip(range(len(alts)), alts)))

    return choices


def get_segment_and_unstack(spec, segment):
    """
    This does what it says.  Take the spec, get the column from the spec for
    the given segment, and unstack.  It is assumed that the last column of
    the multiindex is alternatives so when you do this unstacking,
    each alternative is in a column (which is the format this as used for the
    simple_simulate call.  The weird nuance here is the "Rowid" column -
    since many expressions are repeated (e.g. many are just "1") a Rowid
    column is necessary to identify which alternatives are actually part of
    which original row - otherwise the unstack is incorrect (i.e. the index
    is not unique)
    """
    return spec[segment].unstack().\
        reset_index(level="Rowid", drop=True).fillna(0)


@orca.step()
def tour_mode_choice_simulate(tours_merged,
                              tour_mode_choice_spec,
                              tour_mode_choice_settings,
                              skims, stacked_skims,
                              omx_file,
                              trace_hh_id):

    if trace_hh_id:
        tracer = tracing.get_tracer()
        tracer.info("tour_mode_choice_simulate tracing household %s" % trace_hh_id)

    tours = tours_merged.to_frame()

    choices_list = []

    tracing.print_summary('tour_mode_choice_simulate tour_type',
                          tours.tour_type, value_counts=True)

    for tour_type, segment in tours.groupby('tour_type'):

        logger.info("running tour_type '%s'" % tour_type)

        if trace_hh_id:
            tracer.info("tour_mode_choice_simulate running %s tour_type '%s'" %
                        (len(segment.index), tour_type, ))

        tour_type_tours = tours[tours.tour_type == tour_type]
        orig_key = 'TAZ'
        dest_key = 'destination'

        # FIXME - check that destination is not null (patch_mandatory_tour_destination not run?)

        tracing.print_summary('tour_mode_choice_simulate %s dest_taz' % tour_type,
                              tour_type_tours[dest_key], value_counts=True)

        choices = _mode_choice_simulate(
            tour_type_tours,
            skims, stacked_skims,
            orig_key=orig_key,
            dest_key=dest_key,
            spec=get_segment_and_unstack(tour_mode_choice_spec, tour_type),
            additional_constants=tour_mode_choice_settings['CONSTANTS'],
            omx=omx_file)

        tracing.print_summary('tour_mode_choice_simulate %s' % tour_type,
                              choices, value_counts=True)

        choices_list.append(choices)

        # FIXME - force garbage collection
        mem = asim.memory_info()
        logger.info('memory_info tour_type %s, %s' % (tour_type, mem))

    choices = pd.concat(choices_list)

    tracing.print_summary('tour_mode_choice_simulate all tour type',
                          choices, value_counts=True)

    orca.add_column("tours", "mode", choices)

    if trace_hh_id:
        trace_columns = ['mode']
        tracing.trace_df(orca.get_table('tours').to_frame(),
                         label="mode",
                         slicer='tour_id',
                         index_label='tour_id',
                         columns=trace_columns)

    # FIXME - this forces garbage collection
    asim.memory_info()


@orca.step()
def trip_mode_choice_simulate(tours_merged,
                              trip_mode_choice_spec,
                              trip_mode_choice_settings,
                              skims,
                              stacked_skims,
                              omx_file,
                              trace_hh_id):

    if trace_hh_id:
        tracer = tracing.get_tracer()
        tracer.info("tour_mode_choice_simulate tracing household %s" % trace_hh_id)

    # FIXME - running the trips model on tours
    logger.error('trips not implemented running the trips model on tours')

    trips = tours_merged.to_frame()
    stack = askim.SkimStack(skims)

    choices_list = []

    # FIXME - log
    print "Trip types:\n", trips.tour_type.value_counts()

    for tour_type, segment in trips.groupby('tour_type'):

        logger.info("running tour_type '%s'" % tour_type)

        if trace_hh_id:
            tracer.info("trip_mode_choice_simulate running %s tour_type '%s'" %
                        (len(segment.index), tour_type, ))

        tour_type_tours = trips[trips.tour_type == tour_type]
        orig_key = 'TAZ'
        dest_key = 'destination'

        # FIXME - check that destination is not null (patch_mandatory_tour_destination not run?)

        tracing.print_summary('trip_mode_choice_simulate %s dest_taz' % tour_type,
                              tour_type_tours[dest_key], value_counts=True)

        # FIXME - log
        # print "dest_taz counts:\n", tour_type_tours[dest_key].value_counts()

        choices = _mode_choice_simulate(
            tour_type_tours,
            skims, stacked_skims,
            orig_key=orig_key,
            dest_key=dest_key,
            spec=get_segment_and_unstack(trip_mode_choice_spec, tour_type),
            additional_constants=trip_mode_choice_settings['CONSTANTS'],
            omx=omx_file)

        tracing.print_summary('trip_mode_choice_simulate %s' % tour_type,
                              choices, value_counts=True)

        choices_list.append(choices)

        # FIXME - force garbage collection
        mem = asim.memory_info()
        logger.info('memory_info tour_type %s, %s' % (tour_type, mem))

    choices = pd.concat(choices_list)

    tracing.print_summary('trip_mode_choice_simulate all tour type',
                          choices, value_counts=True)

    # FIXME - is this a NOP if trips table doesn't exist
    orca.add_column("trips", "mode", choices)

    # if trace_hh_id:
    #     trace_columns = ['mode']
    #     tracing.trace_df(orca.get_table('trips').to_frame(),
    #                      label = "mode",
    #                      slicer='tour_id',
    #                      index_label='tour_id',
    #                      columns = trace_columns)

    # FIXME - this forces garbage collection
    asim.memory_info()