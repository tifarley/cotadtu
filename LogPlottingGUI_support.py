import sys
import pandas as pd
from numpy import ndarray
import matplotlib.pyplot as plt

# Gets rid of a Pandas warning when converting timestamps
pd.plotting.register_matplotlib_converters()

import tkinter as tk
import tkinter.ttk as ttk
from tkinter import filedialog, messagebox
py3 = True

def get_id_col(cols):
    rx_id_col = None
    if 'Client ID' in cols:
        rx_id_col = 'Client ID'
    elif 'Long ID' in cols:
        rx_id_col = 'Long ID'
    elif 'RX ID' in cols:
        rx_id_col = 'RX ID'

    return rx_id_col

def plot_data():
    global w, df
    sel_col = w.columnListBox.curselection()

    if df is None or len(sel_col) < 1:
        return

    cols = df.columns
    rx_id_col = get_id_col(cols)

    fig, ax = plt.subplots(nrows=len(sel_col), ncols=1, sharex=True, sharey=False)
    plt.tight_layout()
    plt.subplots_adjust(left=0.10, right=0.82, bottom=0.05, top=0.95)
    if type(ax) != ndarray:
        ax = (ax,)
    for i,c in enumerate(sel_col):
        col = w.columnListBox.get(c)
        sel_rx = w.rxListBox.curselection()
        for rx in sel_rx:
            rxid = w.rxListBox.get(rx)
            selected_data = df.loc[df[rx_id_col] == rxid][col]
            shortID = "0x" + str(rxid[-4:])
            try:
                selected_data.plot(label=shortID, ax=ax[i])
            except Exception as e:
                messagebox.showerror('Error', f'{e}')
            ax[i].set_title(col)
    handles, labels = ax[0].get_legend_handles_labels()
    ax[0].legend(handles, labels, loc=(1.01,0.5))
    root.attributes("-topmost", False)
    plt.show()

def open_file():
    global fname, df

    # Timestamp formats for Venus and Orion logging scripts
    FMT1= "%a_%b_%d_%Y_%H_%M_%S"
    FMT2= "%Y_%m_%d_%H_%M_%S"

    fname = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
    if fname == '':
        return

    try:
        df = pd.read_csv(fname, delimiter=",",index_col=0)
    except Exception as e:
        messagebox.showerror('Error', f'{e}')
        return

    try:
        df.index = pd.to_datetime(df.index, format=FMT1, utc=True)
    except:
        try:
            df.index = pd.to_datetime(df.index, format=FMT2, utc=True)
        except Exception as e:
            messagebox.showerror('Error', f'{e}')
            return
    cols = df.columns
    df = df.dropna(how='all', axis=1)
    
    rx_id_col = get_id_col(cols)
    if rx_id_col is None:
        messagebox.showerror('Error', 'No receiver ID column found in file')
        return

    w.rxListBox.delete(0, 'end')
    w.columnListBox.delete(0, 'end')

    for c in df[rx_id_col].unique():
        if str(c)[:2] == '0x':
            w.rxListBox.insert('end', str(c))

    for col in cols:
        w.columnListBox.insert('end', col)
    root.attributes("-topmost", True)

def init(top, gui, *args, **kwargs):
    global w, top_level, root, df, fname
    df = None
    fname = None
    w = gui
    top_level = top
    root = top

def destroy_window():
    global top_level
    top_level.destroy()
    top_level = None

if __name__ == '__main__':
    import LogPlottingGUI
    LogPlottingGUI.vp_start_gui()





