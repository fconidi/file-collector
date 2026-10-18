"""Native GTK desktop application."""

from pathlib import Path
import threading

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, Pango

from . import __version__
from .core import Filters, make_plan, scan
from .i18n import LANGUAGES, system_language, translate
from .transfer import collect, history, restore

ASSETS = Path(__file__).parent
PRESETS = ("", "pdf,cbr,cbz", "pdf,odt,doc,docx,txt,rtf,ods,xls,xlsx", "jpg,jpeg,png,webp,tif,tiff,svg,heic", "mp3,flac,ogg,wav,m4a", None)


def human_size(value):
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{value} B"
        value /= 1024


def styled(widget, name):
    widget.get_style_context().add_class(name)
    return widget


class Window(Gtk.ApplicationWindow):
    def __init__(self, application):
        super().__init__(application=application, title="File Collector")
        self.set_default_size(1180, 800)
        self.set_size_request(860, 600)
        self.set_icon_from_file(str(ASSETS / "icon.svg"))
        styled(self, "collector")
        self.language = system_language()
        self.dark = bool(Gtk.Settings.get_default().get_property("gtk-application-prefer-dark-theme"))
        self.sources = []
        self.destination = None
        self.files = []
        self.searched = False
        self.busy = False
        self.last_errors = []
        self.cancel = threading.Event()
        self.values = {}
        self.connect("delete-event", self.on_close)
        provider = Gtk.CssProvider()
        provider.load_from_path(str(ASSETS / "style.css"))
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.build()

    def tr(self, message, **values):
        return translate(message, self.language).format(**values)

    def themed(self, dialog):
        context = dialog.get_style_context()
        context.add_class("collector")
        if self.dark:
            context.add_class("dark")
        return dialog

    def label(self, text, css=None):
        widget = Gtk.Label(label=self.tr(text), xalign=0)
        if css:
            styled(widget, css)
        return widget

    def button(self, text, callback, css=None):
        widget = Gtk.Button(label=self.tr(text))
        widget.connect("clicked", callback)
        if css:
            styled(widget, css)
        return widget

    def build(self):
        self.building = True
        self.controls = []
        self.entries = {}
        self.outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(self.outer)
        header = styled(Gtk.Box(spacing=12), "masthead")
        header.pack_start(Gtk.Image.new_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_scale(str(ASSETS / "icon.svg"), 36, 36, True)), False, False, 0)
        header.pack_start(self.label("File Collector", "brand"), False, False, 0)
        header.pack_start(Gtk.Label(), True, True, 0)
        self.language_combo = Gtk.ComboBoxText()
        for code, name in LANGUAGES.items():
            self.language_combo.append(code, name)
        self.language_combo.set_active_id(self.language)
        self.language_combo.set_tooltip_text(self.tr("Language"))
        self.language_combo.get_accessible().set_name(self.tr("Language"))
        self.language_combo.connect("changed", self.change_language)
        self.theme = Gtk.ComboBoxText()
        self.theme.append("light", self.tr("Light"))
        self.theme.append("dark", self.tr("Dark"))
        self.theme.set_active_id("dark" if self.dark else "light")
        self.theme.set_tooltip_text(self.tr("Appearance"))
        self.theme.get_accessible().set_name(self.tr("Appearance"))
        self.theme.connect("changed", self.change_theme)
        self.history_button = self.button("History", self.show_history, "flat")
        settings = Gtk.MenuButton()
        settings.set_image(Gtk.Image.new_from_icon_name("open-menu-symbolic", Gtk.IconSize.BUTTON))
        settings.set_tooltip_text(self.tr("Settings"))
        settings.get_accessible().set_name(self.tr("Settings"))
        styled(settings, "flat")
        popover = Gtk.Popover()
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        panel.set_border_width(14)
        for caption, combo in (("Language", self.language_combo), ("Appearance", self.theme)):
            panel.pack_start(self.label(caption, "field-label"), False, False, 0)
            panel.pack_start(combo, False, False, 0)
        panel.show_all()
        popover.add(panel)
        settings.set_popover(popover)
        for widget in (self.history_button, settings):
            header.pack_start(widget, False, False, 0)
            self.controls.append(widget)
        self.outer.pack_start(header, False, False, 0)
        body = Gtk.Box()
        self.outer.pack_start(body, True, True, 0)
        sidebar_scroll = styled(Gtk.ScrolledWindow(), "sidebar-scroll")
        sidebar_scroll.set_overlay_scrolling(False)
        sidebar_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sidebar_scroll.set_size_request(286, -1)
        self.sidebar = styled(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12), "sidebar")
        sidebar_scroll.add(self.sidebar)
        self.controls.append(self.sidebar)
        body.pack_start(sidebar_scroll, False, False, 0)
        self.sidebar.pack_start(self.label("Source folders", "section-title"), False, False, 0)
        source_scroll = Gtk.ScrolledWindow()
        source_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        source_scroll.set_min_content_height(90)
        source_scroll.set_max_content_height(130)
        self.source_list = styled(Gtk.ListBox(), "origin-list")
        source_scroll.add(self.source_list)
        self.sidebar.pack_start(source_scroll, False, False, 0)
        actions = Gtk.Box(spacing=6)
        actions.pack_start(self.button("Add folders", self.add_sources, "outlined"), True, True, 0)
        self.remove_button = self.button("Remove", self.remove_source, "flat")
        actions.pack_start(self.remove_button, False, False, 0)
        self.sidebar.pack_start(actions, False, False, 0)
        self.sidebar.pack_start(Gtk.Separator(), False, False, 3)
        self.sidebar.pack_start(self.label("File types", "section-title"), False, False, 0)
        self.presets = Gtk.ComboBoxText()
        for name in ("All files", "Comics", "Documents", "Images", "Audio", "Custom"):
            self.presets.append_text(self.tr(name))
        self.presets.set_active(self.values.get("preset", 0))
        self.presets.connect("changed", self.apply_preset)
        self.sidebar.pack_start(self.presets, False, False, 0)
        self.field(self.sidebar, "extensions", "Extensions, separated by commas", "pdf,cbr,cbz")
        self.field(self.sidebar, "name", "Name contains", "Optional text")
        advanced = Gtk.Expander(label=self.tr("Advanced filters"))
        fields = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        fields.set_margin_top(10)
        for key, label, placeholder in (
            ("min_size", "Minimum size (MiB)", "0"),
            ("max_size", "Maximum size (MiB)", ""),
            ("after", "Modified from (YYYY-MM-DD)", "2026-01-01"),
            ("before", "Modified through (YYYY-MM-DD)", "2026-12-31"),
            ("max_depth", "Depth (0 = source only)", "Unlimited"),
            ("excluded", "Excluded folder names", "__MACOSX, .git"),
        ):
            self.field(fields, key, label, placeholder)
        self.hidden = Gtk.CheckButton(label=self.tr("Include hidden files"))
        self.hidden.set_active(self.values.get("hidden", False))
        self.hidden.connect("toggled", self.invalidate)
        fields.pack_start(self.hidden, False, False, 0)
        advanced.add(fields)
        self.sidebar.pack_start(advanced, False, False, 0)
        self.search_button = self.button("Search files", self.start_search, "primary")
        self.sidebar.pack_start(self.search_button, False, False, 4)

        workspace = styled(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12), "workspace")
        body.pack_start(workspace, True, True, 0)
        toolbar = Gtk.Box(spacing=8)
        toolbar.pack_start(self.label("Results", "section-title"), True, True, 0)
        self.count_label = styled(Gtk.Label(), "badge")
        toolbar.pack_start(self.count_label, False, False, 0)
        toolbar.pack_start(self.button("Select all", lambda *_: self.select_all(True), "flat"), False, False, 0)
        toolbar.pack_start(self.button("Select none", lambda *_: self.select_all(False), "flat"), False, False, 0)
        workspace.pack_start(toolbar, False, False, 0)
        self.controls.append(toolbar)
        self.stack = styled(Gtk.Stack(), "results")
        self.stack.set_transition_type(Gtk.StackTransitionType.NONE)
        workspace.pack_start(self.stack, True, True, 0)
        empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, valign=Gtk.Align.CENTER, halign=Gtk.Align.CENTER)
        empty.set_margin_start(20)
        empty.set_margin_end(20)
        empty.pack_start(Gtk.Image.new_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_scale(str(ASSETS / "icon.svg"), 116, 116, True)), False, False, 0)
        self.empty_title = self.label("Your files, together", "empty-title")
        self.empty_title.set_xalign(.5)
        self.empty_text = self.label("Choose source folders, then search.\nReview the files before moving them.", "muted")
        self.empty_text.set_justify(Gtk.Justification.CENTER)
        self.empty_text.set_line_wrap(True)
        empty.pack_start(self.empty_title, False, False, 0)
        empty.pack_start(self.empty_text, False, False, 0)
        self.stack.add_named(empty, "empty")
        self.model = Gtk.ListStore(bool, str, str, str, str, int)
        self.tree = Gtk.TreeView(model=self.model)
        self.tree.set_enable_search(True)
        self.tree.set_search_column(1)
        self.tree.set_tooltip_column(2)
        toggle = Gtk.CellRendererToggle()
        toggle.connect("toggled", self.toggle_file)
        self.tree.append_column(Gtk.TreeViewColumn("", toggle, active=0))
        for index, name, width in ((1, "File", 120), (2, "Source folder", 150), (3, "Size", 85), (4, "Destination name", 160)):
            cell = Gtk.CellRendererText(ellipsize=Pango.EllipsizeMode.MIDDLE, ypad=8, xpad=6)
            if index == 3:
                cell.set_property("xalign", 1.0)
            column = Gtk.TreeViewColumn(self.tr(name), cell, text=index)
            if index == 3:
                column.set_alignment(1.0)
            column.set_resizable(True)
            column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
            column.set_fixed_width(width)
            column.set_expand(index in (1, 2, 4))
            column.set_min_width(width)
            self.tree.append_column(column)
        self.tree.connect("row-activated", lambda *_: self.open_source())
        scroll = Gtk.ScrolledWindow()
        scroll.add(self.tree)
        self.stack.add_named(scroll, "files")
        self.controls.append(self.tree)
        selection = Gtk.Box(spacing=8)
        self.selected_label = self.label("Ready", "muted")
        selection.pack_start(self.selected_label, True, True, 0)
        selection.pack_start(self.button("Open source folder", lambda *_: self.open_source(), "flat"), False, False, 0)
        workspace.pack_start(selection, False, False, 0)
        self.controls.append(selection)
        workspace.pack_start(Gtk.Label(), False, False, 0)

        destination = styled(Gtk.Box(spacing=12), "destination")
        self.controls.append(destination)
        destination_text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        destination_text.pack_start(self.label("Destination", "section-title"), False, False, 0)
        self.destination_label = self.label("No destination selected", "muted")
        self.destination_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        self.destination_label.set_max_width_chars(45)
        destination_text.pack_start(self.destination_label, False, False, 0)
        destination.pack_start(destination_text, True, True, 0)
        choose_button = self.button("Choose folder", self.choose_destination, "outlined")
        choose_button.set_valign(Gtk.Align.CENTER)
        destination.pack_start(choose_button, False, False, 0)
        policy_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        policy_box.pack_start(self.label("Name conflicts", "field-label"), False, False, 0)
        self.policy = Gtk.ComboBoxText()
        self.policy.append("rename", self.tr("Keep both (add suffix)"))
        self.policy.append("skip", self.tr("Skip existing names"))
        self.policy.set_active_id(self.values.get("policy", "rename"))
        self.policy.connect("changed", lambda *_: self.refresh_selection())
        policy_box.pack_start(self.policy, False, False, 0)
        destination.pack_start(policy_box, False, False, 0)
        self.move_button = self.button("Preview and move", self.show_preview, "accent")
        self.move_button.set_valign(Gtk.Align.CENTER)
        destination.pack_start(self.move_button, False, False, 0)
        self.outer.pack_start(destination, False, False, 0)
        self.progress = Gtk.ProgressBar()
        self.outer.pack_start(self.progress, False, False, 0)
        status = styled(Gtk.Box(spacing=10), "statusbar")
        self.status = self.label("Ready", "muted")
        self.status.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        status.pack_start(self.status, True, True, 0)
        self.details_button = self.button("Details", lambda *_: self.show_details())
        status.pack_start(self.details_button, False, False, 0)
        self.cancel_button = self.button("Cancel", self.request_cancel)
        status.pack_start(self.cancel_button, False, False, 0)
        status.pack_start(styled(Gtk.Label(label=__version__), "muted"), False, False, 0)
        self.outer.pack_start(status, False, False, 0)
        self.building = False
        self.show_all()
        self.refresh_sources()
        self.populate()
        self.change_theme()
        self.set_busy(False)

    def field(self, parent, key, label, placeholder):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        caption = self.label(label, "field-label")
        entry = Gtk.Entry()
        entry.set_placeholder_text(self.tr(placeholder))
        entry.set_text(self.values.get(key, ""))
        entry.get_accessible().set_name(self.tr(label))
        caption.set_mnemonic_widget(entry)
        entry.connect("changed", self.invalidate)
        box.pack_start(caption, False, False, 0)
        box.pack_start(entry, False, False, 0)
        self.entries[key] = entry
        parent.pack_start(box, False, False, 0)

    def change_language(self, combo):
        if self.building or self.busy:
            return
        self.values = {key: entry.get_text() for key, entry in self.entries.items()}
        self.values.update(preset=self.presets.get_active(), hidden=self.hidden.get_active(), policy=self.policy.get_active_id())
        selected = {file.path for file in self.selected_files()}
        self.language = combo.get_active_id()
        self.outer.destroy()
        self.build()
        for row in self.model:
            row[0] = self.files[row[5]].path in selected
        self.refresh_selection()

    def change_theme(self, *_):
        self.dark = self.theme.get_active_id() == "dark"
        context = self.get_style_context()
        (context.add_class if self.dark else context.remove_class)("dark")

    def invalidate(self, *_):
        if self.building or self.busy:
            return
        self.files = []
        self.searched = False
        self.populate()
        self.status.set_text(self.tr("Search again after changing source folders or filters."))

    def apply_preset(self, combo):
        value = PRESETS[combo.get_active()]
        if value is not None:
            self.entries["extensions"].set_text(value)

    def refresh_sources(self):
        for row in self.source_list.get_children():
            row.destroy()
        for path in self.sources:
            label = Gtk.Label(label=path.name or str(path), xalign=0)
            label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
            label.set_tooltip_text(str(path))
            self.source_list.add(label)
        self.source_list.show_all()
        self.remove_button.set_sensitive(bool(self.sources))
        self.search_button.set_sensitive(bool(self.sources))
        if self.destination:
            self.destination_label.set_text(str(self.destination))
            self.destination_label.set_tooltip_text(str(self.destination))

    def chooser(self, title, multiple, callback):
        chooser = Gtk.FileChooserNative.new(self.tr(title), self, Gtk.FileChooserAction.SELECT_FOLDER, self.tr("Choose"), self.tr("Cancel"))
        chooser.set_select_multiple(multiple)
        chooser.set_create_folders(not multiple)
        if self.destination and not multiple:
            chooser.set_current_folder(str(self.destination))
        def response(dialog, result):
            if result == Gtk.ResponseType.ACCEPT:
                callback([Path(name).resolve() for name in dialog.get_filenames()])
            dialog.destroy()
            self.chooser_dialog = None
        chooser.connect("response", response)
        self.chooser_dialog = chooser
        chooser.show()

    def add_sources(self, *_):
        def chosen(paths):
            self.sources = list(dict.fromkeys(self.sources + paths))
            self.invalidate()
            self.refresh_sources()
        self.chooser("Add folders", True, chosen)

    def remove_source(self, *_):
        row = self.source_list.get_selected_row()
        if row:
            del self.sources[row.get_index()]
            self.invalidate()
            self.refresh_sources()

    def choose_destination(self, *_):
        def chosen(paths):
            if paths:
                self.destination = paths[0]
                self.refresh_sources()
                self.refresh_selection()
        self.chooser("Destination", False, chosen)

    def get_filters(self):
        values = {key: entry.get_text().strip() for key, entry in self.entries.items()}
        for key in ("min_size", "max_size"):
            value = values[key]
            values[key] = int(float(value.replace(",", ".")) * 1024 * 1024) if value else (0 if key == "min_size" else None)
        values["max_depth"] = int(values["max_depth"]) if values["max_depth"] else None
        return Filters(**values, hidden=self.hidden.get_active())

    def set_busy(self, busy, message="Ready"):
        self.busy = busy
        for widget in self.controls:
            widget.set_sensitive(not busy)
        self.cancel_button.set_visible(busy)
        self.details_button.set_visible(bool(self.last_errors) and not busy)
        if not busy:
            self.refresh_selection()
            self.search_button.set_sensitive(bool(self.sources))
        self.status.set_text(self.tr(message))

    def work(self, message, action, done):
        self.cancel = threading.Event()
        self.progress.set_fraction(0)
        self.set_busy(True, message)
        def finish(result, error):
            self.set_busy(False)
            if error:
                self.last_errors = [str(error)]
                self.status.set_text(self.tr("Operation failed"))
                self.details_button.show()
                self.show_details()
            else:
                done(result)
            return False
        def worker():
            try:
                result = action()
            except Exception as error:
                GLib.idle_add(finish, None, error)
            else:
                GLib.idle_add(finish, result, None)
        threading.Thread(target=worker, daemon=False).start()

    def start_search(self, *_):
        try:
            filters = self.get_filters()
        except (ValueError, OverflowError):
            self.message("Check your settings", self.tr("Use positive sizes, valid ISO dates and a whole-number depth."))
            return
        sources, destination = list(self.sources), self.destination
        self.work("Searching…", lambda: scan(sources, filters, destination, self.cancel), self.search_done)

    def search_done(self, result):
        self.files = result.files
        self.last_errors = result.errors
        self.searched = not result.cancelled
        self.populate()
        self.progress.set_fraction(0 if result.cancelled else 1)
        self.status.set_text(self.tr("Search cancelled; results are partial" if result.cancelled else "Search complete"))
        self.details_button.set_visible(bool(self.last_errors))

    def populate(self):
        self.model.clear()
        for index, file in enumerate(self.files):
            self.model.append([True, file.path.name, str(file.path.parent), human_size(file.size), "", index])
        self.stack.set_visible_child_name("files" if self.files else "empty")
        none_found = self.searched and not self.files
        self.empty_title.set_text(self.tr("No matching files" if none_found else "Your files, together"))
        self.empty_text.set_text(self.tr("Try different filters or add another source folder." if none_found else "Choose source folders, then search.\nReview the files before moving them."))
        self.count_label.set_text(self.tr("{count} files", count=len(self.files)))
        self.refresh_selection()

    def selected_files(self):
        return [self.files[row[5]] for row in self.model if row[0]]

    def refresh_selection(self):
        if self.building:
            return
        files = self.selected_files()
        self.selected_label.set_text(self.tr("{count} selected · {size}", count=len(files), size=human_size(sum(f.size for f in files))))
        self.move_button.set_sensitive(bool(files and self.destination) and not self.busy)
        names = {}
        if self.destination:
            try:
                plan = make_plan(files, self.destination, self.policy.get_active_id())
                names = {item.file.path: self.tr("Skip") if item.skip else item.target.name for item in plan}
            except (ValueError, OSError):
                self.move_button.set_sensitive(False)
        for row in self.model:
            row[4] = names.get(self.files[row[5]].path, "")

    def toggle_file(self, _, path):
        self.model[path][0] = not self.model[path][0]
        self.refresh_selection()

    def select_all(self, selected):
        for row in self.model:
            row[0] = selected
        self.refresh_selection()

    def open_source(self):
        model, iterator = self.tree.get_selection().get_selected()
        if iterator is not None:
            try:
                Gio.AppInfo.launch_default_for_uri(self.files[model[iterator][5]].path.parent.as_uri(), None)
            except GLib.Error as error:
                self.message("Operation failed", str(error))

    def show_preview(self, *_):
        try:
            plan = make_plan(self.selected_files(), self.destination, self.policy.get_active_id())
        except (ValueError, OSError) as error:
            self.message("Check your settings", str(error))
            return
        dialog = self.themed(Gtk.Dialog(title=self.tr("Preview collection"), transient_for=self, modal=True))
        dialog.set_default_size(760, 480)
        dialog.add_button(self.tr("Cancel"), Gtk.ResponseType.CANCEL)
        confirm = dialog.add_button(self.tr("Move selected files"), Gtk.ResponseType.ACCEPT)
        styled(confirm, "accent")
        confirm.set_sensitive(any(not item.skip for item in plan))
        dialog.set_default_response(Gtk.ResponseType.CANCEL)
        box = dialog.get_content_area()
        box.set_spacing(12)
        box.set_border_width(18)
        box.pack_start(Gtk.Label(label=str(self.destination), xalign=0, selectable=True, wrap=True), False, False, 0)
        box.pack_start(Gtk.Label(label=self.tr("{move} to move · {skip} to skip · {rename} renamed", move=sum(not p.skip for p in plan), skip=sum(p.skip for p in plan), rename=sum(p.renamed for p in plan)), xalign=0), False, False, 0)
        text = "\n".join(f"{item.file.path}\n    → {self.tr('Skip') if item.skip else item.target.name}\n" for item in plan)
        box.pack_start(self.text_view(text), True, True, 0)
        box.pack_start(Gtk.Label(label=self.tr("Original archives and unselected files stay where they are."), xalign=0, wrap=True), False, False, 0)
        dialog.show_all()
        accepted = dialog.run() == Gtk.ResponseType.ACCEPT
        dialog.destroy()
        if accepted:
            self.work("Moving…", lambda: collect(plan, cancel=self.cancel, progress=self.transfer_progress), self.transfer_done)

    def transfer_progress(self, count, total, name):
        def update():
            self.progress.set_fraction(count / max(total, 1))
            self.status.set_text(f"{count} / {total}   {name}")
            return False
        GLib.idle_add(update)

    def transfer_done(self, result, restoring=False):
        self.files = []
        self.searched = False
        self.populate()
        self.last_errors = result.errors
        title = "Operation cancelled" if result.cancelled else ("Restore complete" if restoring else "Collection complete")
        summary = self.tr("Moved: {moved}    Skipped: {skipped}    Errors: {errors}", moved=result.moved, skipped=result.skipped, errors=len(result.errors))
        self.status.set_text(summary)
        self.progress.set_fraction(0 if result.cancelled else 1)
        self.details_button.set_visible(bool(result.errors))
        self.message(title, summary)

    def request_cancel(self, *_):
        self.cancel.set()
        self.status.set_text(self.tr("Cancelling…"))

    def on_close(self, *_):
        if self.busy:
            self.request_cancel()
            return True
        return False

    def show_history(self, *_):
        try:
            entries = history()
        except Exception as error:
            self.message("Operation failed", str(error))
            return
        if not entries:
            self.message("History", self.tr("No collections recorded"))
            return
        dialog = self.themed(Gtk.Dialog(title=self.tr("History"), transient_for=self, modal=True))
        dialog.set_default_size(680, 400)
        dialog.add_button(self.tr("Close"), Gtk.ResponseType.CLOSE)
        styled(dialog.add_button(self.tr("Restore selected collection"), Gtk.ResponseType.ACCEPT), "accent")
        box = dialog.get_content_area()
        box.set_border_width(18)
        box.set_spacing(14)
        box.pack_start(Gtk.Label(label=self.tr("Only unchanged files with a free original path can be restored."), xalign=0, wrap=True), False, False, 0)
        listing = Gtk.ListBox()
        for run_id, created, count in entries:
            row = Gtk.Label(label=f"{created} UTC     {self.tr('{count} files', count=count)}", xalign=0)
            row.set_margin_top(10)
            row.set_margin_bottom(10)
            listing.add(row)
        scroll = styled(Gtk.ScrolledWindow(), "dialog-surface")
        scroll.set_shadow_type(Gtk.ShadowType.NONE)
        scroll.add(listing)
        box.pack_start(scroll, True, True, 0)
        listing.select_row(listing.get_row_at_index(0))
        dialog.show_all()
        accepted = dialog.run() == Gtk.ResponseType.ACCEPT
        selected = listing.get_selected_row()
        index = selected.get_index() if selected else None
        dialog.destroy()
        if accepted and index is not None:
            run_id = entries[index][0]
            self.work("Restoring…", lambda: restore(run_id, cancel=self.cancel, progress=self.transfer_progress), lambda result: self.transfer_done(result, True))

    @staticmethod
    def text_view(text):
        view = Gtk.TextView(editable=False, cursor_visible=False, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        view.set_left_margin(12)
        view.set_right_margin(12)
        view.set_top_margin(8)
        view.set_bottom_margin(8)
        view.get_buffer().set_text(text)
        scroll = styled(Gtk.ScrolledWindow(), "dialog-surface")
        scroll.set_shadow_type(Gtk.ShadowType.NONE)
        scroll.add(view)
        return scroll

    def show_details(self):
        dialog = self.themed(Gtk.Dialog(title=self.tr("Details"), transient_for=self, modal=True))
        dialog.set_default_size(760, 420)
        dialog.add_button(self.tr("Close"), Gtk.ResponseType.CLOSE)
        dialog.get_content_area().pack_start(self.text_view("\n\n".join(self.last_errors)), True, True, 0)
        dialog.show_all()
        dialog.run()
        dialog.destroy()

    def message(self, title, text):
        dialog = self.themed(Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.INFO,
                                               buttons=Gtk.ButtonsType.CLOSE, text=self.tr(title)))
        dialog.format_secondary_text(text)
        dialog.run()
        dialog.destroy()


def main():
    application = Gtk.Application(application_id="org.syslinuxos.FileCollector")
    def activate(app):
        window = app.get_active_window()
        if window is None:
            window = Window(app)
        window.present()
    application.connect("activate", activate)
    application.run(None)


if __name__ == "__main__":
    main()
