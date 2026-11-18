"""Diálogo de prévia PS1: ambos os painéis usam a conversão do exportador."""
from __future__ import annotations

import base64
from dataclasses import asdict
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from .core import ModError
from .ps1_image_optimizer import (ImageOptions, render_card, png_rgba,
    rgb555, MODES, PALETTES, FILTERS, DITHERS)
from .tables import CARD_COUNT

MODES_LABEL = {"automatico": "Automático (recomendado)",
               "maxima_fidelidade": "Máxima fidelidade",
               "compatibilidade": "Compatibilidade original",
               "personalizado": "Personalizado"}
PALETTE_LABEL = {"automatico": "Automático (seguro)",
                 "compatibilidade": "CLUT original",
                 "seguro": "Otimização segura",
                 "personalizada": "Paleta personalizada"}
FILTER_LABEL = {"automatico": "Automático", "lanczos": "Lanczos",
                "bicubic": "Bicubic", "bilinear": "Bilinear",
                "nearest": "Nearest Neighbor", "box": "Área (BOX)"}
DITHER_LABEL = {"automatico": "Automático", "nenhum": "Sem dithering",
                "floyd": "Floyd–Steinberg", "bayer2": "Bayer 2×2",
                "bayer4": "Bayer 4×4", "bayer8": "Bayer 8×8"}


class ImageOptimizerDialog(tk.Toplevel):
    def __init__(self, master, project, cid):
        super().__init__(master)
        self.project, self.cid = project, int(cid)
        self.title(f"Prévia real PS1 — carta #{self.cid:03d}")
        self.geometry("1110x800")
        self.minsize(820, 620)
        self.transient(master)
        self._images = []
        self._source = project.art_path(cid)
        if not self._source or not self._source.is_file():
            self.destroy()
            raise ModError(f"Carta #{cid}: importe primeiro a imagem original.")
        self._load_cluts(master)
        defaults = ImageOptions.from_mapping(project.metadata.get("ps1_image_optimizer"))
        self.enabled = tk.BooleanVar(value=defaults.enabled)
        self.params = {}
        for field, labels in (("mode", MODES_LABEL), ("palette", PALETTE_LABEL),
                              ("resample", FILTER_LABEL), ("dither", DITHER_LABEL)):
            self.params[field] = tk.StringVar(value=labels[getattr(defaults, field)])
        self.strength = tk.DoubleVar(value=defaults.intensity)
        self.manual = {name: tk.DoubleVar(value=getattr(defaults, name))
                       for name in ("brightness", "contrast", "saturation",
                                    "gamma", "sharpness")}
        self.denoise = tk.BooleanVar(value=defaults.denoise)
        self.zoom = tk.StringVar(value="200%")
        self.resource = tk.StringVar(value="Arte 102×96")
        self.show_adjusted = tk.BooleanVar(value=False)
        self._build()
        self._refresh()

    def _load_cluts(self, parent):
        from .ps1_mod import read_linked_wa
        source = Path(self.project.metadata.get("base_source") or "")
        if not source.is_file() or source.suffix.lower() not in (".bin", ".cue"):
            filename = filedialog.askopenfilename(
                parent=parent, title="Selecione o BIN/CUE ORIGINAL vinculado ao projeto",
                filetypes=[("PS1 BIN/CUE", "*.bin *.cue")])
            if not filename:
                self.destroy()
                raise ModError("Prévia cancelada: é necessário o WA_MRG.MRG de origem.")
            source = Path(filename)
        wa = read_linked_wa(self.project, source)  # confere hashes SLUS/WA
        if self.cid <= CARD_COUNT:
            model = self.cid
            native = True
        else:
            from .ps1_expansion import native_model, PS1_CARD_CAPACITY
            if self.cid > PS1_CARD_CAPACITY:
                self.destroy()
                raise ModError(
                    f"Carta #{self.cid}: acima do limite PS1 de {PS1_CARD_CAPACITY}. "
                    "A imagem continuará disponível apenas no Studio.")
            model = native_model(self.project, self.cid)
            native = False
        self.native = native
        art_off = ((model - 1) * 7 + CARD_COUNT) * 2048
        thumb_off = (model - 1) * 2048
        self.art_record = wa[art_off:art_off + 7 * 2048]
        self.thumb_record = wa[thumb_off:thumb_off + 2048]
        if len(self.art_record) != 7 * 2048 or len(self.thumb_record) != 2048:
            self.destroy()
            raise ModError("Registro de arte/miniatura está incompleto na imagem escolhida.")

    def _build(self):
        controls = ttk.Frame(self, padding=12)
        controls.pack(fill="x")
        ttk.Checkbutton(controls, text="Otimização PS1 ATIVADA",
                        variable=self.enabled).grid(row=0, column=0, sticky="w", pady=4)
        for col, (field, labels, title) in enumerate((
            ("mode", MODES_LABEL, "Perfil"),
            ("palette", PALETTE_LABEL, "CLUT"),
            ("resample", FILTER_LABEL, "Redimensionamento"),
            ("dither", DITHER_LABEL, "Dithering"))):
            ttk.Label(controls, text=title).grid(row=1, column=col, sticky="w", padx=3)
            ttk.Combobox(controls, values=list(labels.values()), textvariable=self.params[field],
                         state="readonly", width=22).grid(row=2, column=col, padx=3, sticky="ew")
        ttk.Label(controls, text="Intensidade de dithering (0–100%)").grid(row=3,column=0,sticky="w")
        ttk.Scale(controls, from_=0, to=1, variable=self.strength).grid(
            row=3,column=1,sticky="ew",padx=3)
        ttk.Label(controls, text="Visualização").grid(row=3,column=2,sticky="e")
        resources=ttk.Combobox(controls, values=["Arte 102×96", "Miniatura 40×32"],
                     textvariable=self.resource,state="readonly",width=17)
        resources.grid(row=3,column=3,sticky="ew")
        resources.bind("<<ComboboxSelected>>",lambda _e:self._redraw())
        advanced=ttk.LabelFrame(self,text="Ajustes manuais (usados no perfil Personalizado)",padding=7)
        advanced.pack(fill="x",padx=12,pady=3)
        for i, (name, val) in enumerate(self.manual.items()):
            ttk.Label(advanced,text={"brightness":"Brilho","contrast":"Contraste",
                                     "saturation":"Saturação","gamma":"Gama",
                                     "sharpness":"Nitidez"}[name]).grid(row=0,column=i,sticky="w",padx=4)
            ttk.Spinbox(advanced,from_=.7,to=1.5,increment=.05,width=8,
                        textvariable=val).grid(row=1,column=i,padx=4,sticky="w")
        ttk.Checkbutton(advanced,text="Redução de ruído",variable=self.denoise).grid(
            row=1,column=5,padx=8)
        action=ttk.Frame(self,padding=(12,4))
        action.pack(fill="x")
        ttk.Button(action,text="Recalcular prévia",command=self._refresh).pack(side="left")
        ttk.Button(action,text="Salvar configuração no projeto",command=self._save).pack(side="right")
        ttk.Button(action,text="Fechar",command=self.destroy).pack(side="right",padx=8)
        ttk.Checkbutton(action,text="Mostrar pré-indexação em vez do original",
                        variable=self.show_adjusted,
                        command=self._redraw).pack(side="left",padx=(16,5))
        ttk.Label(action,text="Zoom").pack(side="left",padx=(18,5))
        zoom=ttk.Combobox(action,values=["100%","200%","400%","800%"],
                          state="readonly",textvariable=self.zoom,width=7)
        zoom.pack(side="left")
        zoom.bind("<<ComboboxSelected>>",lambda _e:self._redraw())
        self.panels=[]
        frames=ttk.Frame(self,padding=8)
        frames.pack(fill="both",expand=True)
        for col,title in enumerate(("PNG ORIGINAL (enquadramento sem ajustes)", "PS1 REAL — ÍNDICES + CLUT")):
            frame=ttk.LabelFrame(frames,text=title,padding=5)
            frame.grid(row=0,column=col,sticky="nsew",padx=5)
            canvas=tk.Canvas(frame,width=425,height=310,bg="#161c2b",highlightthickness=0)
            ys=ttk.Scrollbar(frame,orient="vertical",command=canvas.yview)
            xs=ttk.Scrollbar(frame,orient="horizontal",command=canvas.xview)
            canvas.configure(xscrollcommand=xs.set,yscrollcommand=ys.set)
            canvas.grid(row=0,column=0,sticky="nsew")
            ys.grid(row=0,column=1,sticky="ns")
            xs.grid(row=1,column=0,sticky="ew")
            frame.rowconfigure(0,weight=1)
            frame.columnconfigure(0,weight=1)
            self.panels.append(canvas)
        frames.columnconfigure(0,weight=1)
        frames.columnconfigure(1,weight=1)
        frames.rowconfigure(0,weight=1)
        footer=ttk.Frame(self,padding=9)
        footer.pack(fill="x")
        self.info=tk.StringVar()
        ttk.Label(footer,textvariable=self.info,wraplength=1000,
                  justify="left").pack(anchor="w")
        self.palette_canvas=tk.Canvas(footer,width=800,height=46,bg="#141a27",
                                      highlightthickness=0)
        self.palette_canvas.pack(fill="x",pady=4)

    def _options(self):
        def key(field, choices):
            current = self.params[field].get()
            return next((k for k,v in choices.items() if v==current),None)
        return ImageOptions.from_mapping({
            "enabled":self.enabled.get(),
            "mode":key("mode",MODES_LABEL),
            "palette":key("palette",PALETTE_LABEL),
            "resample":key("resample",FILTER_LABEL),
            "dither":key("dither",DITHER_LABEL),
            "intensity":float(self.strength.get()),
            "denoise":self.denoise.get(),
            **{name:float(var.get()) for name,var in self.manual.items()},
        })

    def _refresh(self):
        try:
            from .ps1_image_optimizer import _scaled_rgba
            self.rendered = render_card(self._source,self.art_record,
                                        self.thumb_record,self._options(),
                                        private_clut=False)
            neutral=ImageOptions(mode="maxima_fidelidade",resample="lanczos")
            self.reference_art=_scaled_rgba(self._source,self.rendered.art.size,neutral)[0]
            self.reference_thumb=_scaled_rgba(self._source,self.rendered.thumbnail.size,neutral)[0]
            self._redraw()
        except (OSError,ValueError,tk.TclError,ModError) as exc:
            messagebox.showerror("Conversão PS1",str(exc),parent=self)

    def _redraw(self):
        if not hasattr(self,"rendered"):
            return
        resource = (self.rendered.art if self.resource.get().startswith("Arte")
                    else self.rendered.thumbnail)
        z=int(self.zoom.get().rstrip("%"))//100
        original=(self.reference_art if resource is self.rendered.art
                  else self.reference_thumb)
        if self.show_adjusted.get():
            original=resource.source_rgba
        self._images.clear()
        for canvas, pixels in zip(self.panels,(original,resource.preview_rgba)):
            payload=png_rgba(pixels,resource.size)
            photo=tk.PhotoImage(data=base64.b64encode(payload).decode("ascii"))
            if z!=1:
                photo=photo.zoom(z,z)
            self._images.append(photo)
            canvas.delete("all")
            canvas.create_image(0,0,anchor="nw",image=photo)
            canvas.configure(scrollregion=(0,0,photo.width(),photo.height()))
        report=resource.report
        source_label=("ID original" if self.native else "ID expandido (723–740)")
        warnings="; ".join(report["avisos"]) or "CLUT original preservada"
        self.info.set(
            f"{source_label} • {report['resolucao']} • "
            f"{report['cores_usadas']}/{report['cores_clut']} índices • "
            f"Dithering: {report['dithering']} • RMSE RGB: {report['rmse_rgb']} • "
            f"Fidelidade indicativa: {report['fidelidade_indicativa']}/100\n"
            f"{warnings}. A qualidade só é confirmada em jogo após testar o BIN no ePSXe.")
        self.palette_canvas.delete("all")
        used=sorted(set(resource.indices))
        for j,idx in enumerate(used[:72]):
            r,g,b,a=rgb555(resource.clut[idx])
            x,y=(j%36)*21,(j//36)*19
            color=f"#{r:02x}{g:02x}{b:02x}" if a else "#303846"
            self.palette_canvas.create_rectangle(x+2,y+2,x+19,y+17,fill=color,outline="#777")
        if len(used)>72:
            self.palette_canvas.create_text(780,23,text=f"+{len(used)-72}",fill="white")

    def _save(self):
        try:
            data=asdict(self._options())
            self.project.metadata["ps1_image_optimizer"]=data
            self.project.save()  # gera backup normal do projeto
        except (OSError,ValueError,ModError) as exc:
            messagebox.showerror("Configuração PS1",str(exc),parent=self)
            return
        if hasattr(self.master, "_refresh_project"):
            self.master._refresh_project()
        messagebox.showinfo("Otimização PS1",
                            "Configuração salva. O mesmo pipeline será usado ao gerar o BIN/CUE.",
                            parent=self)
