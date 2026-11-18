"""Janela de edição em massa com prévia obrigatória e commit único."""
import tkinter as tk
from tkinter import ttk, messagebox

from .bulk_editor import OPERATIONS, plan_bulk, commit_bulk
from .core import ModError
from .tables import CARD_COUNT
from .expanded import display_name


class BulkEditDialog(tk.Toplevel):
    def __init__(self, owner, project, cards, ids, *, source, original_prices, on_changed):
        super().__init__(owner)
        self.project = project
        self.cards = cards
        self.ids = tuple(sorted(set(int(cid) for cid in ids)))
        self.original_prices = original_prices
        self.on_changed = on_changed
        self.title('Edição em massa — Baú e Password')
        self.geometry('830x650')
        self.minsize(720, 530)
        self.transient(owner)
        self.copies_on = tk.BooleanVar(value=source == 'chest')
        self.prices_on = tk.BooleanVar(value=source == 'price')
        self.copies_op = tk.StringVar(value='definir')
        self.prices_op = tk.StringVar(value='definir')
        self.copies_val = tk.StringVar(value='1')
        self.prices_val = tk.StringVar(value='100')
        self.preview_rows = None
        form = ttk.Frame(self, padding=14)
        form.pack(fill='both', expand=True)
        ttk.Label(form, text=f'{len(self.ids)} cartas selecionadas', font=('Segoe UI', 12, 'bold')).pack(anchor='w')
        ttk.Label(form, text=('Cópias no baú correspondem ao Studio/simulador. O jogo PS1 usa '
                              'Memory Card; não alteramos a coleção do .mcr.'),
                  wraplength=740).pack(anchor='w', pady=(4, 9))
        for title, enabled, op, value in (
                ('Quantidade no baú do Studio', self.copies_on, self.copies_op, self.copies_val),
                ('Custo do Password no PS1', self.prices_on, self.prices_op, self.prices_val)):
            line=ttk.Frame(form)
            line.pack(fill='x', pady=4)
            ttk.Checkbutton(line,text=title,variable=enabled).pack(side='left')
            ttk.Label(line,text='Operação:').pack(side='left',padx=(22,4))
            ttk.Combobox(line,values=OPERATIONS,state='readonly',
                         textvariable=op,width=13).pack(side='left')
            ttk.Label(line,text='Valor:').pack(side='left',padx=(12,4))
            ttk.Entry(line,textvariable=value,width=14).pack(side='left')
        ttk.Label(form,text='Use Definir, Adicionar, Subtrair ou Zerar. Campos desmarcados não são alterados.').pack(anchor='w',pady=(4,8))
        ttk.Button(form,text='Calcular prévia das mudanças',
                   command=self.preview).pack(anchor='w',pady=(2,9))
        ttk.Label(form,text='PRÉVIA — antes / depois',font=('Segoe UI',10,'bold')).pack(anchor='w')
        table=ttk.Frame(form)
        table.pack(fill='both',expand=True)
        self.tree=ttk.Treeview(table,show='headings',
            columns=('id','nome','qtd_antes','qtd_depois','preco_antes','preco_depois'),
            height=10)
        for field,label,width in (
            ('id','ID',58),('nome','Carta',220),
            ('qtd_antes','Baú atual',90),('qtd_depois','Baú novo',90),
            ('preco_antes','Estrelas atuais',120),('preco_depois','Estrelas novas',120)):
            self.tree.heading(field,text=label)
            self.tree.column(field,width=width,stretch=field=='nome')
        bar=ttk.Scrollbar(table,orient='vertical',command=self.tree.yview)
        self.tree.configure(yscrollcommand=bar.set)
        self.tree.pack(side='left',fill='both',expand=True)
        bar.pack(side='right',fill='y')
        buttons=ttk.Frame(form)
        buttons.pack(fill='x',pady=(10,0))
        ttk.Button(buttons,text='Cancelar',command=self.destroy).pack(side='right')
        self.confirm_button=ttk.Button(buttons,text='Confirmar alterações',
                                       state='disabled',command=self.commit)
        self.confirm_button.pack(side='right',padx=8)
        for value in (self.copies_on,self.prices_on,self.copies_op,self.prices_op,
                      self.copies_val,self.prices_val):
            value.trace_add('write',lambda *_:self._invalidate())
        self.bind('<Escape>',lambda _e:self.destroy())
        self.preview()

    def _invalidate(self):
        self.preview_rows = None
        if hasattr(self,'confirm_button'):
            self.confirm_button.configure(state='disabled')

    def preview(self):
        try:
            copies=(self.copies_op.get(),self.copies_val.get()) if self.copies_on.get() else None
            prices=(self.prices_op.get(),self.prices_val.get()) if self.prices_on.get() else None
            rows=plan_bulk(self.project,self.ids,copies=copies,price=prices,
                           original_prices=self.original_prices)
        except (ModError, ValueError, OverflowError) as exc:
            self._invalidate()
            messagebox.showerror('Edição em massa',str(exc),parent=self)
            return
        self.tree.delete(*self.tree.get_children())
        for row in rows:
            self.tree.insert('', 'end', iid=str(row.cid), values=(
                f'{row.cid:03d}',display_name(row.cid,self.cards),
                row.copies_before,row.copies_after,
                row.price_before if row.price_before is not None else '—',
                row.price_after if row.price_after is not None else '—'))
        self.preview_rows=rows
        self.confirm_button.configure(state='normal')

    def commit(self):
        if not self.preview_rows:
            messagebox.showinfo('Edição em massa','Calcule a prévia antes de confirmar.',parent=self)
            return
        try:
            # Recalcular, evitando aplicar valores antigos após outra mudança no projeto.
            copies=(self.copies_op.get(),self.copies_val.get()) if self.copies_on.get() else None
            prices=(self.prices_op.get(),self.prices_val.get()) if self.prices_on.get() else None
            fresh=plan_bulk(self.project,self.ids,copies=copies,price=prices,
                            original_prices=self.original_prices)
            if fresh != self.preview_rows:
                self._invalidate()
                messagebox.showwarning('Prévia alterada',
                    'Os valores atuais mudaram. Recalcule a prévia antes de confirmar.',parent=self)
                return
            count=commit_bulk(self.project,fresh,copies=copies is not None,
                              price=prices is not None)
        except (ModError,ValueError,OSError) as exc:
            messagebox.showerror('Falha na edição em massa',str(exc),parent=self)
            return
        self.on_changed()
        self.destroy()
        messagebox.showinfo('Edição concluída',
                            f'{count} carta(s) editada(s) e salvas no projeto.',parent=self.master)
