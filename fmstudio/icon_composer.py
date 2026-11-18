"""Seleção acumulativa de ícones de descrição com confirmação atômica."""
import tkinter as tk
from tkinter import ttk
from .richtext import CUSTOM_ICONS, NATIVE_ICONS


class IconComposer(tk.Toplevel):
    def __init__(self, master, get_icon, on_confirm):
        super().__init__(master)
        self.title('Ícones de descrição — aplicar vários')
        self.geometry('750x670')
        self.minsize(550,440)
        self.transient(master)
        self.get_icon=get_icon
        self.on_confirm=on_confirm
        self.pending=[]
        self.images=[]
        self.items=[]
        self.search=tk.StringVar()
        self.group=tk.StringVar(value='Todos')
        panel=ttk.Frame(self,padding=13)
        panel.pack(fill='both',expand=True)
        ttk.Label(panel,text='Escolha um ícone, clique Aplicar e continue selecionando. '
                  'A descrição só será alterada após OK.',wraplength=700).pack(anchor='w')
        filters=ttk.Frame(panel)
        filters.pack(fill='x',pady=(8,3))
        ttk.Entry(filters,textvariable=self.search).pack(side='left',fill='x',expand=True)
        ttk.Combobox(filters,textvariable=self.group,values=['Todos','Studio','Nativos'],
                     state='readonly',width=13).pack(side='left',padx=(8,0))
        display=ttk.Frame(panel)
        display.pack(fill='both',expand=True)
        list_frame=ttk.Frame(display)
        list_frame.pack(side='left',fill='both',expand=True)
        self.listbox=tk.Listbox(list_frame,height=16,exportselection=False,
                                selectmode='browse',font=('Segoe UI',10))
        vscroll=ttk.Scrollbar(list_frame,command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=vscroll.set)
        self.listbox.pack(side='left',fill='both',expand=True)
        vscroll.pack(side='right',fill='y')
        preview=ttk.Frame(display,padding=(12,8))
        preview.pack(side='right',fill='y')
        ttk.Label(preview,text='Prévia do ícone').pack(anchor='w')
        self.preview=ttk.Label(preview,text='Selecione um ícone')
        self.preview.pack(pady=12)
        ttk.Button(preview,text='Aplicar',command=self.apply).pack(fill='x')
        ttk.Button(preview,text='Remover último',command=self.pop).pack(fill='x',pady=5)
        ttk.Label(panel,text='Ícones preparados (ainda não gravados):').pack(anchor='w',pady=(10,3))
        self.composition=tk.Text(panel,height=4,wrap='word',state='disabled')
        self.composition.pack(fill='x')
        line=ttk.Frame(panel)
        line.pack(fill='x',pady=(10,0))
        self.counter=tk.StringVar(value='0 ícones preparados')
        ttk.Label(line,textvariable=self.counter).pack(side='left')
        ttk.Button(line,text='Cancelar',command=self.destroy).pack(side='right')
        ttk.Button(line,text='OK — inserir todos',command=self.confirm).pack(side='right',padx=8)
        self.search.trace_add('write',lambda *_:self.refresh())
        self.group.trace_add('write',lambda *_:self.refresh())
        self.listbox.bind('<<ListboxSelect>>',self.update_preview)
        self.listbox.bind('<Double-1>',lambda _e:self.apply())
        self.bind('<Escape>',lambda _e:self.destroy())
        self.refresh()

    def refresh(self):
        q=self.search.get().strip().casefold()
        group=self.group.get()
        items=[]
        if group in ('Todos','Studio'):
            for name,label in CUSTOM_ICONS.items():
                if q in label.casefold() or q in name.casefold():
                    items.append((label,f'{{icon:{name}}}',name))
        if group in ('Todos','Nativos'):
            for name,code in NATIVE_ICONS.items():
                if q in name.casefold() or q in f'{code:02x}':
                    items.append((f'{name} — F8 0B {code:02X}',f'{{f8 0B {code:02X}}}',None))
        self.items=items
        self.listbox.delete(0,'end')
        for label,_,_ in items:
            self.listbox.insert('end',label)
        if items:
            self.listbox.selection_set(0)
        self.update_preview()

    def update_preview(self,_event=None):
        chosen=self.listbox.curselection()
        if not chosen:
            self.preview.configure(image='',text='Nenhum ícone selecionado')
            return
        _,_,name=self.items[chosen[0]]
        img=self.get_icon(name) if name else None
        if img:
            enlarged=img.zoom(4,4)
            self.images=[enlarged]
            self.preview.configure(image=enlarged,text='')
        else:
            self.images=[]
            self.preview.configure(image='',text='Ícone nativo PS1' if name is None else name)

    def apply(self):
        chosen=self.listbox.curselection()
        if not chosen:
            return
        self.pending.append(self.items[chosen[0]][1])
        self.composition.configure(state='normal')
        self.composition.insert('end',self.pending[-1]+' ')
        self.composition.configure(state='disabled')
        self.counter.set(f'{len(self.pending)} ícones preparados')

    def pop(self):
        if not self.pending:
            return
        self.pending.pop()
        self._redraw()

    def _redraw(self):
        self.composition.configure(state='normal')
        self.composition.delete('1.0','end')
        self.composition.insert('1.0',' '.join(self.pending))
        self.composition.configure(state='disabled')
        self.counter.set(f'{len(self.pending)} ícones preparados')

    def confirm(self):
        if self.pending:
            self.on_confirm(list(self.pending))
        self.destroy()
