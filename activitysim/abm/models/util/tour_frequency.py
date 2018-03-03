# ActivitySim
# See full license in LICENSE.txt.

import itertools
import numpy as np
import pandas as pd


TOUR_CATEGORIES = ['mandatory', 'non_mandatory', 'subtour']


def enumerate_tour_types(tour_flavors):
    # tour_flavors: {'eat': 1, 'business': 2, 'maint': 1}
    # channels:      ['eat1', 'business1', 'business2', 'maint1']
    channels = [tour_type + str(tour_num)
                for tour_type, max_count in tour_flavors.iteritems()
                for tour_num in range(1, max_count + 1)]
    return channels


def canonical_tours():
    """
        create labels for every the possible tour by combining tour_type/tour_num.

    Returns
    -------
        list of canonical tour labels in alphabetical order
    """

    # FIXME we pathalogically know what the possible tour_types and their max tour_nums are
    # FIXME instead, should get flavors from alts tables (but we would have to know their names...)
    # alts = orca.get_table('non_mandatory_tour_frequency_alts').local
    # non_mandatory_tour_flavors = {c : alts[c].max() for c in alts.columns}

    # - non_mandatory_channels
    non_mandatory_tour_flavors = {'escort': 2, 'shopping': 1, 'othmaint': 1, 'othdiscr': 1,
                                  'eatout': 1, 'social': 1}
    non_mandatory_channels = enumerate_tour_types(non_mandatory_tour_flavors)

    # - mandatory_channels
    mandatory_tour_flavors = {'work': 2, 'school': 2}
    mandatory_channels = enumerate_tour_types(mandatory_tour_flavors)

    # - atwork_subtour_channels
    # we need to distinguish between subtours of different work tours
    # (e.g. eat1_1 is eat subtour for parent work tour 1 and eat1_2 is for work tour 2)
    atwork_subtour_flavors = {'eat': 1, 'business': 2, 'maint': 1}
    atwork_subtour_channels = enumerate_tour_types(atwork_subtour_flavors)
    max_work_tours = mandatory_tour_flavors['work']
    atwork_subtour_channels = ['%s_%s' % (c, i+1)
                               for c in atwork_subtour_channels
                               for i in range(max_work_tours)]

    sub_channels = non_mandatory_channels + mandatory_channels + atwork_subtour_channels
    sub_channels.sort()

    return sub_channels


def set_tour_index(tours, parent_tour_num_col=None):
    """

    Parameters
    ----------
    tours : DataFrame
        Tours dataframe to reindex.
        The new index values are stable based on the person_id, tour_type, and tour_num.
        The existing index is ignored and replaced.

        This gives us a stable (predictable) tour_id
        It also simplifies attaching random number streams to tours that are stable
        (even across simulations)
    """

    tour_num_col = 'tour_type_num'
    possible_tours = canonical_tours()
    possible_tours_count = len(possible_tours)

    assert tour_num_col in tours.columns

    tours['tour_id'] = tours.tour_type + tours[tour_num_col].map(str)

    if parent_tour_num_col:
        # we need to distinguish between subtours of different work tours
        # (e.g. eat1_1 is eat subtour for parent work tour 1 and eat1_2 is for work tour 2)
        tours['tour_id'] = tours['tour_id'] + '_' + tours[parent_tour_num_col].map(str)

    # map recognized strings to ints
    tours.tour_id = tours.tour_id.replace(to_replace=possible_tours,
                                          value=range(possible_tours_count))

    # convert to numeric - shouldn't be any NaNs - this will raise error if there are
    tours.tour_id = pd.to_numeric(tours.tour_id, errors='coerce').astype(int)

    tours.tour_id = (tours.person_id * possible_tours_count) + tours.tour_id

    # if tours.tour_id.duplicated().any():
    #     print "\ntours.tour_id not unique\n", tours[tours.tour_id.duplicated(keep=False)]
    assert not tours.tour_id.duplicated().any()

    tours.set_index('tour_id', inplace=True, verify_integrity=True)


def process_tours(tour_frequency, tour_frequency_alts, tour_category, parent_col='person_id'):
    """
    This method processes the tour_frequency column that comes
    out of the model of the same name and turns into a DataFrame that
    represents the tours that were generated

    Parameters
    ----------
    tour_frequency: Series
        A series which has person id as the index and the chosen alternative
        index as the value
    tour_frequency_alts: DataFrame
        A DataFrame which has as a unique index which relates to the values
        in the series above typically includes columns which are named for trip
        purposes with values which are counts for that trip purpose.  Example
        trip purposes include escort, shopping, othmaint, othdiscr, eatout,
        social, etc.  A row would be an alternative which might be to take
        one shopping trip and zero trips of other purposes, etc.
    tour_category : str
        one of 'mandatory', 'non_mandatory' or 'subtour' to add consistent tour_category columns
        or None (as in the case of joint tours) if no tour_category fields should be added to tours

    Returns
    -------
    tours : DataFrame
        An example of a tours DataFrame is supplied as a comment in the
        source code - it has an index which is a unique tour identifier,
        a person_id column, and a tour type column which comes from the
        column names of the alternatives DataFrame supplied above.

    tours.tour_type       - tour type (e.g. school, work, shopping, eat)
    tours.tour_type_num   - if there are two 'school' type tours, they will be numbered 1 and 2
    tours.tour_type_count - number of tours of tour_type parent has (parent's max tour_type_num)
    tours.tour_num        - index of tour (of any type) for parent
    tours.tour_count      - number of tours of any type) for parent (parent's max tour_num)
    """

    # get the actual alternatives for each person - have to go back to the
    # non_mandatory_tour_frequency_alts dataframe to get this - the choice
    # above just stored the index values for the chosen alts
    tours = tour_frequency_alts.loc[tour_frequency]

    # assign person ids to the index
    tours.index = tour_frequency.index

    """
               alt1       alt2     alt3
    PERID
    2588676       2         0         0
    2588677       1         1         0
    """

    # reformat with the columns given below
    tours = tours.stack().reset_index()
    tours.columns = [parent_col, "tour_type", "tour_type_count"]

    """
        <parent_col> tour_type  tour_type_count
    0     2588676    alt1           2
    1     2588676    alt2           0
    2     2588676    alt3           0
    3     2588676    alt1           1
    4     2588677    alt2           1
    5     2588677    alt3           0

    parent_col is the index from non_mandatory_tour_frequency
    tour_type is the column name from non_mandatory_tour_frequency_alts
    tour_type_count is the count value of the tour's chosen alt's tour_type from alts table
    """

    # now do a repeat and a take, so if you have two trips of given type you
    # now have two rows, and zero trips yields zero rows
    tours = tours.take(np.repeat(tours.index.values, tours.tour_type_count.values))

    grouped = tours.groupby([parent_col, 'tour_type'])
    tours['tour_type_num'] = grouped.cumcount() + 1
    tours['tour_type_count'] = tours['tour_type_num'] + grouped.cumcount(ascending=False)

    grouped = tours.groupby(parent_col)
    tours['tour_num'] = grouped.cumcount() + 1
    tours['tour_count'] = tours['tour_num'] + grouped.cumcount(ascending=False)

    """
        <parent_col> tour_type  tour_type_num  tour_type_count tour_num  tour_count
    0     2588676       alt1           1           2               1         4
    0     2588676       alt1           2           2               2         4
    0     2588676       alt2           1           1               3         4
    0     2588676       alt3           1           1               4         4
    """

    # set these here to ensure consistency across different tour categories
    if tour_category is not None:
        assert tour_category in ['mandatory', 'non_mandatory', 'subtour']
        tours['mandatory'] = (tour_category == 'mandatory')
        tours['non_mandatory'] = (tour_category == 'non_mandatory')
        tours['tour_category'] = tour_category

    return tours


def process_mandatory_tours(persons, mandatory_tour_frequency_alts):
    """
    This method processes the mandatory_tour_frequency column that comes out of
    the model of the same name and turns into a DataFrame that represents the
    mandatory tours that were generated

    Parameters
    ----------
    persons : DataFrame
        Persons is a DataFrame which has a column call
        mandatory_tour_frequency (which came out of the mandatory tour
        frequency model) and a column is_worker which indicates the person's
        worker status.  The only valid values of the mandatory_tour_frequency
        column to take are "work1", "work2", "school1", "school2" and
        "work_and_school"

    Returns
    -------
    tours : DataFrame
        An example of a tours DataFrame is supplied as a comment in the
        source code - it has an index which is a tour identifier, a person_id
        column, a tour_type column which is "work" or "school" and a tour_num
        column which is set to 1 or 2 depending whether it is the first or
        second mandatory tour made by the person.  The logic for whether the
        work or school tour comes first given a "work_and_school" choice
        depends on the is_worker column: work tours first for workers, second for non-workers
    """

    PERSON_COLUMNS = ["mandatory_tour_frequency", "is_worker", "school_taz", "workplace_taz"]
    assert not persons.mandatory_tour_frequency.isnull().any()

    tours = process_tours(persons.mandatory_tour_frequency.dropna(),
                          mandatory_tour_frequency_alts,
                          tour_category='mandatory')

    tours_merged = pd.merge(tours[['person_id', 'tour_type']],
                            persons[PERSON_COLUMNS],
                            left_on='person_id', right_index=True)

    # by default work tours are first for work_and_school tours
    # swap tour_nums for non-workers so school tour is 1 and work is 2
    work_and_school_and_student = \
        (tours_merged.mandatory_tour_frequency == 'work_and_school') & ~tours_merged.is_worker

    tours.tour_num = tours.tour_num.where(~work_and_school_and_student, 3 - tours.tour_num)

    # work tours destination is workplace_taz, school tours destination is school_taz
    tours['destination'] = \
        tours_merged.workplace_taz.where((tours_merged.tour_type == 'work'),
                                         tours_merged.school_taz)

    # assign stable (predictable) tour_id
    set_tour_index(tours)

    """
               person_id tour_type  tour_type_count  tour_type_num  tour_num  tour_count
    tour_id
    12413245      827549    school                2              1         1           2
    12413244      827549    school                2              2         2           2
    12413264      827550      work                1              1         1           2
    12413266      827550    school                1              1         2           2
    ...
               mandatory  non_mandatory tour_category  destination

                    True          False     mandatory          102
                    True          False     mandatory          102
                    True          False     mandatory            9
                    True          False     mandatory          102
    """
    return tours


def process_non_mandatory_tours(non_mandatory_tour_frequency,
                                non_mandatory_tour_frequency_alts):
    """
    This method processes the non_mandatory_tour_frequency column that comes
    out of the model of the same name and turns into a DataFrame that
    represents the non mandatory tours that were generated

    Parameters
    ----------
    non_mandatory_tour_frequency: Series
        A series which has person id as the index and the chosen alternative
        index as the value
    non_mandatory_tour_frequency_alts: DataFrame
        A DataFrame which has as a unique index which relates to the values
        in the series above typically includes columns which are named for trip
        purposes with values which are counts for that trip purpose.  Example
        trip purposes include escort, shopping, othmaint, othdiscr, eatout,
        social, etc.  A row would be an alternative which might be to take
        one shopping trip and zero trips of other purposes, etc.

    Returns
    -------
    tours : DataFrame
        An example of a tours DataFrame is supplied as a comment in the
        source code - it has an index which is a unique tour identifier,
        a person_id column, and a tour type column which comes from the
        column names of the alternatives DataFrame supplied above.
    """
    tours = process_tours(non_mandatory_tour_frequency,
                          non_mandatory_tour_frequency_alts,
                          tour_category='non_mandatory')

    # assign stable (predictable) tour_id
    set_tour_index(tours)

    """
               person_id tour_type  tour_type_count  tour_type_num  tour_num   tour_count
    tour_id
    17008286     1133885  shopping                1              1         1            3
    17008283     1133885  othmaint                1              1         2            3
    17008282     1133885  othdiscr                1              1         3            3
    ...
               mandatory  non_mandatory  tour_category

                   False           True  non_mandatory
                   False           True  non_mandatory
                   False           True  non_mandatory
    """

    return tours


def process_atwork_subtours(work_tours, atwork_subtour_frequency_alts):

    """
    This method processes the atwork_subtour_frequency column that comes
    out of the model of the same name and turns into a DataFrame that
    represents the subtours tours that were generated

    Parameters
    ----------
    work_tours: DataFrame
        A series which has parent work tour tour_id as the index and
        columns with person_id and atwork_subtour_frequency.
    atwork_subtour_frequency_alts: DataFrame
        A DataFrame which has as a unique index with atwork_subtour_frequency values
        and frequency counts for the subtours to be generated for that choice

    Returns
    -------
    tours : DataFrame
        An example of a tours DataFrame is supplied as a comment in the
        source code - it has an index which is a unique tour identifier,
        a person_id column, and a tour type column which comes from the
        column names of the alternatives DataFrame supplied above.
    """

    # print atwork_subtour_frequency_alts
    """
                  eat  business  maint
    alt
    no_subtours     0         0      0
    eat             1         0      0
    business1       0         1      0
    maint           0         0      1
    business2       0         2      0
    eat_business    1         1      0
    """

    parent_col = 'parent_tour_id'
    tours = process_tours(work_tours.atwork_subtour_frequency.dropna(),
                          atwork_subtour_frequency_alts,
                          tour_category='subtour',
                          parent_col=parent_col)

    # print tours
    """
               parent_tour_id tour_type  tour_type_count  tour_type_num  tour_num  tour_count
    tour_id
    77147972         77147984       eat                1              1         1           2
    77401056         77147984     maint                1              1         2           2
    80893007         80893019       eat                1              1         1           1

              mandatory  non_mandatory tour_category
                  False          False       subtour
                  False          False       subtour
                  False          False       subtour
    """

    # merge person_id from parent work_tours
    work_tours = work_tours[["person_id", "tour_num"]]
    work_tours.rename(columns={'tour_num': 'parent_tour_num'}, inplace=True)
    tours = pd.merge(tours, work_tours, left_on=parent_col, right_index=True)

    # assign stable (predictable) tour_id
    set_tour_index(tours, parent_tour_num_col='parent_tour_num')

    """
               person_id tour_type  tour_type_count  tour_type_num  tour_num  tour_count
    tour_id
    77147972     5143198       eat                1              1         1           2
    77401056     5143198     maint                1              1         2           2
    80893007     5392867       eat                1              1         1           1

              mandatory  non_mandatory tour_category   parent_tour_id

                  False          False       subtour         77147984
                  False          False       subtour         77147984
                  False          False       subtour         80893019
    """

    return tours


JOINT_TOUR_OWNER_ID_COL = 'household_id'


def set_joint_tour_index(tours, alts):
    """

    Parameters
    ----------
    tours : DataFrame
        Tours dataframe to reindex.
        The new index values are stable based on the person_id, tour_type, and tour_num.
        The existing index is ignored and replaced.

        This gives us a stable (predictable) tour_id
        It also simplifies attaching random number streams to tours that are stable
        (even across simulations)
    """

    tour_num_col = 'tour_type_num'
    index_name = 'joint_tour_id'

    # canonical_joint_tours

    tour_flavors = {c: alts[c].max() for c in alts.columns}
    possible_tours = enumerate_tour_types(tour_flavors)

    possible_tours.sort()
    possible_tours_count = len(possible_tours)

    # e.g. 'shop1', 'shop2', 'visit1'
    tours[index_name] = tours.tour_type + tours[tour_num_col].map(str)

    # map recognized strings to ints
    tours[index_name] = tours[index_name].replace(to_replace=possible_tours,
                                                  value=range(possible_tours_count))

    # convert to numeric - shouldn't be any NaNs - this will raise error if there are
    tours[index_name] = pd.to_numeric(tours[index_name], errors='coerce').astype(int)

    tours[index_name] = (tours[JOINT_TOUR_OWNER_ID_COL] * possible_tours_count) + tours[index_name]

    # if tours[index_name].duplicated().any():
    #     print "\ntours index not unique\n", tours[tours[index_name].duplicated(keep=False)]
    assert not tours[index_name].duplicated().any()

    tours.set_index(index_name, inplace=True, verify_integrity=True)


def process_joint_tours(joint_tour_frequency, joint_tour_frequency_alts):
    """
    This method processes the joint_tour_frequency column that comes out of
    the model of the same name and turns into a DataFrame that represents the
    joint tours that were generated

    Parameters
    ----------
    joint_tour_frequency : pandas.Series
        houeshold joint_tour_frequency (which came out of the joint tour frequency model)

    Returns
    -------
    tours : DataFrame
        An example of a tours DataFrame is supplied as a comment in the
        source code - it has an index which is a tour identifier, a household_id
        column, a tour_type column and tour_type_num and tour_num columns
        which is set to 1 or 2 depending whether it is the first or second joint tour
        made by the household.
    """

    assert not joint_tour_frequency.isnull().any()

    tours = process_tours(joint_tour_frequency.dropna(),
                          joint_tour_frequency_alts,
                          tour_category=None,
                          parent_col=JOINT_TOUR_OWNER_ID_COL)

    # assign stable (predictable) tour_id
    set_joint_tour_index(tours, joint_tour_frequency_alts)

    """
                   household_id tour_type  tour_type_count  tour_type_num  tour_num  tour_count
    joint_tour_id
    3209530              320953      disc                1              1         1           2
    3209531              320953      disc                2              2         2           2
    23267026            2326702      shop                1              1         1           1
    17978574            1797857      main                1              1         1           1
    """

    return tours
