import glob
import math
import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt
import matplotlib.ticker as tkr
import os
import pandas as pd
import urbs
import sys

# INIT



def get_most_recent_entry(search_dir):
    """ Return most recently modified entry from given directory.
    
    Args:
        search_dir: an absolute or relative path to a directory
        
    Returns:
        The file/folder in search_dir that has the most recent 'modified'
        datetime.
    """
    entries = glob.glob(os.path.join(search_dir, "*"))
    entries.sort(key=lambda x: os.path.getmtime(x))
    return entries[-1]

def glob_result_files(folder_name):
    """ Glob result spreadsheets from specified folder. 
    
    Args:
        folder_name: an absolute or relative path to a directory
        
    Returns:
        list of filenames that match the pattern 'scenario_*.xlsx'
    """
    glob_pattern = os.path.join(folder_name, 's*.xlsx')
    result_files = sorted(glob.glob(glob_pattern))
    return result_files

def compare_scenarios(result_files, output_filename):
    """ Create report sheet and plots for given report spreadsheets.
    
    Args:
        result_files: a list of spreadsheet filenames generated by urbs.report
        output_filename: a spreadsheet filename that the comparison is to be 
                         written to
                         
     Returns:
        Nothing
    
    To do: 
        Don't use report spreadsheets, instead load pickled problem 
        instances. This would make this function less fragile and dependent
        on the output format of urbs.report().
    """
        
    # derive list of scenario names for column labels/figure captions
    scenario_names = [os.path.basename(rf) # drop folder names, keep filename
                      .replace('_', ' ') # replace _ with spaces
                      .replace('.xlsx', '') # drop file extension
                      .replace('scenario ', '') # drop 'scenario ' prefix
                      for rf in result_files]
    #scenario_names = [s[0:s.find('-')] for s in scenario_names] # drop everything after first '-'
    
    
    # find base scenario and put at first position
    try:
        base_scenario = scenario_names.index('base')
        result_files.insert(0, result_files.pop(base_scenario))
        scenario_names.insert(0, scenario_names.pop(base_scenario))
    except ValueError:
        pass # do nothing if no base scenario is found
    
    costs = []  # total costs by type and scenario
    esums = []  # sum of energy produced by scenario
    caps = []
    
    # READ
    
    for rf in result_files:
        with pd.ExcelFile(rf) as xls:
            cost = xls.parse('Costs',index_col=[0])
            esum = xls.parse('Commodity sums')
            cap = xls.parse('Process caps', index_col=[0,1])
    
            # repair broken MultiIndex in the first column
            esum.reset_index(inplace=True)
            esum.fillna(method='ffill', inplace=True)
            esum.set_index(['index', 'pro'], inplace=True)
            
            cap = cap['Total'].loc['StRupertMayer']
            
            costs.append(cost)
            esums.append(esum)
            caps.append(cap)
    
    # merge everything into one DataFrame each
    costs = pd.concat(costs, axis=1, keys=scenario_names)
    esums = pd.concat(esums, axis=1, keys=scenario_names)
    caps = pd.concat(caps, axis=1, keys=scenario_names)
    
    # ANALYSE
    
    # drop redundant 'costs' column label
    # make index name nicer for plot
    # sort/transpose frame
    # convert EUR/a to 1000 EUR/a
    # only keep cost types with non-zero value around
    costs.columns = costs.columns.droplevel(1)
    costs.index.name = 'Cost type'
    costs = costs.sort_index().transpose()
    costs = costs
    costs = costs.loc[:, costs.sum() > 0]
    
    # sum up created energy over all locations, but keeping scenarios (level=0)
    # make index name 'Commodity' nicer for plot
    # drop all unused commodities and sort/transpose
    # convert MWh to GWh
    created = esums.loc['Created'].sum(axis=1, level=0)
    created.index.name = 'Process'
    used_processes = (created.sum(axis=1) > 0)
    created = created[used_processes].sort_index().transpose()
    created = created
    
    sto_sums = esums.loc[('Storage', 'Retrieved')].sort_index()
    sto_sums = sto_sums
    sto_sums.index = sto_sums.index.droplevel(1)
    sto_sums.name = 'Battery'
    
    # PLOT
    
    fig = plt.figure(figsize=(24, 8))
    gs = gridspec.GridSpec(1, 3, width_ratios=[6, 7, 2], wspace=0.03)
    
    ax0 = plt.subplot(gs[0])
    cost_colors = [urbs.to_color(cost_type) for cost_type in costs.columns]
    bp0 = costs.plot(ax=ax0, kind='barh', color=cost_colors, stacked=True,
                     linewidth=0)
    
    ax1 = plt.subplot(gs[1])
    created_colors = [urbs.to_color(commodity) for commodity in created.columns]
    bp1 = created.plot(ax=ax1, kind='barh', stacked=True, color=created_colors,
                       linewidth=0)
    
    ax2 = plt.subplot(gs[2])
    bp2 = sto_sums.plot(ax=ax2, kind='barh', stacked=True, 
                        color=urbs.to_color('Storage'),
                        linewidth=0)
    
    # remove scenario names from other bar plots
    for ax in [ax1, ax2]:
        ax.set_yticklabels('')

    
    # set limits and ticks for both axes
    for ax in [ax0, ax1, ax2]:
        plt.setp(list(ax.spines.values()), color=urbs.to_color('Grid'))
        ax.yaxis.grid(False)
        ax.xaxis.grid(True, 'major', color=urbs.to_color('Grid'), linestyle='-')
        ax.xaxis.set_ticks_position('none')
        ax.yaxis.set_ticks_position('none')
        
        # group 1,000,000 with commas
        xmin, xmax = ax.get_xlim()
        if xmax > 90:
            group_thousands_and_skip_zero = tkr.FuncFormatter(
                lambda x, pos: '' if int(x) == 0 else '{:0,d}'.format(int(x)))
            ax.xaxis.set_major_formatter(group_thousands_and_skip_zero)
        else:
            skip_lowest = tkr.FuncFormatter(
                lambda x, pos: '' if pos == 0 else x)
            ax.xaxis.set_major_formatter(skip_lowest)
    
        # legend
        lg = ax.legend(frameon=False, loc='lower center',
                       ncol=4,
                       bbox_to_anchor=(0.5, .99))
        plt.setp(lg.get_patches(), edgecolor=urbs.to_color('Decoration'),
                 linewidth=0)
    
    ax0.set_xlabel('Total costs (EUR/a)')
    ax1.set_xlabel('Total energy produced (kWh)')
    ax2.set_xlabel('Retrieved energy (kWh)')
    
    for ext in ['png', 'pdf']:
        fig.savefig('{}.{}'.format(output_filename, ext),
                    bbox_inches='tight')
    
    # REPORT
    with pd.ExcelWriter('{}.{}'.format(output_filename, 'xlsx')) as writer:
        costs.to_excel(writer, 'Costs')
        esums.to_excel(writer, 'Energy sums')
        caps.to_excel(writer, 'Process caps')
        
if __name__ == '__main__':
    
    # add or change plot colors
    my_colors = {
        'Demand': (0, 0, 0),
        'Diesel generator': (218, 215, 203),
        'Electricity': (0, 51, 89),
        'Photovoltaics': (0, 101, 189),
        'Storage': (100, 160, 200),
        'Fix': (128, 128, 128),
        'Inv': (0, 101, 189), #(51, 117, 169),
        'Fuel': (128, 169, 201),
        'Revenue': (204, 220, 233),
        'Var': (128, 153, 172),
        'Fuel': (218, 215, 203), #(51, 92, 122),
        'Purchase': (0, 51, 89),
        'Startup': (204, 214, 222),
        'Grid': (205, 205, 205),
    }
    for country, color in my_colors.items():
        urbs.COLORS[country] = color
    
    directories = sys.argv[1:]
    if not directories:
        # get the directory of the supposedly last run
        # and retrieve (glob) a list of all result spreadsheets from there
        directories = [get_most_recent_entry('result')]
    
    for directory in directories:
        result_files = glob_result_files(directory)
        
        # specify comparison result filename 
        # and run the comparison function
        comp_filename = os.path.join(directory, 'comparison')
        compare_scenarios(list(reversed(result_files)), comp_filename)
