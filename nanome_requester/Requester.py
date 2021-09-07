import nanome
from nanome.util import async_callback

from .API import API


class Requester(nanome.AsyncPluginInstance):
    def start(self):
        self.api = API(self)

        self.menu = nanome.ui.Menu()
        self.menu.title = 'Requester'
        self.menu.width = 0.7
        self.menu.height = 0.7

        ln_header = self.menu.root.create_child_node()
        ln_header.sizing_type = ln_header.SizingTypes.ratio
        ln_header.sizing_value = 0.1
        self.lbl_header = ln_header.add_new_label()
        self.lbl_header.text_horizontal_align = self.lbl_header.HorizAlignOptions.Middle
        self.lbl_header.text_vertical_align = self.lbl_header.VertAlignOptions.Middle
        self.lbl_header.text_max_size = 0.4

        ln_lst = self.menu.root.create_child_node()
        ln_lst.forward_dist = 0.001
        self.lst = ln_lst.add_new_list()

        ln_buttons = self.menu.root.create_child_node()
        ln_buttons.layout_orientation = ln_buttons.LayoutTypes.horizontal
        ln_buttons.sizing_type = ln_buttons.SizingTypes.ratio
        ln_buttons.sizing_value = 0.1
        self.ln_buttons = ln_buttons

        ln_cancel = ln_buttons.create_child_node()
        ln_cancel.set_padding(right=0.005)
        btn_cancel = ln_cancel.add_new_button('cancel')
        btn_cancel.register_pressed_callback(self.cancel_request)

        ln_continue = ln_buttons.create_child_node()
        ln_continue.set_padding(left=0.005)
        btn_continue = ln_continue.add_new_button('continue')
        btn_continue.disable_on_press = True
        btn_continue.register_pressed_callback(self.continue_request)

        self.inputs = []

    def on_run(self):
        self.menu.enabled = True
        self.show_endpoints()
        self.update_menu(self.menu)

    def show_endpoints(self):
        # display list of non-hidden endpoints
        self.lbl_header.text_value = 'Select an endpoint'
        self.lst.items.clear()
        self.lst.display_rows = 7

        for endpoint in self.api.list_endpoints():
            ln = nanome.ui.LayoutNode()
            btn = ln.add_new_button(endpoint['name'])
            btn.endpoint = endpoint
            btn.register_pressed_callback(self.make_request)
            self.lst.items.append(ln)

        self.ln_buttons.enabled = False
        self.update_menu(self.menu)

    def make_request(self, btn):
        self.api.init_request(btn.endpoint)

    def cancel_request(self, btn):
        self.api.reset()
        self.show_endpoints()

    @async_callback
    async def prompt_inputs(self, name, inputs):
        # prompt user for inputs
        self.lbl_header.text_value = name

        self.inputs.clear()
        self.lst.items.clear()
        self.lst.display_rows = 5

        # check if any input is complex
        if any(i['type'] == 'molecule' for i in inputs):
            complexes = await self.request_complex_list()

        for item in inputs:
            ln = nanome.ui.LayoutNode()
            ln.set_padding(top=0.01, down=0.01, left=0.02)
            ln.layout_orientation = ln.LayoutTypes.horizontal

            ln1 = ln.create_child_node()
            ln1.set_padding(right=0.01)
            lbl = ln1.add_new_label(item['label'])
            lbl.text_max_size = 0.4
            lbl.text_vertical_align = lbl.VertAlignOptions.Middle

            ln2 = ln.create_child_node()
            ln2.set_padding(left=0.01)
            ln2.forward_dist = 0.001

            if item['type'] in ['number', 'password', 'text']:
                inp = ln2.add_new_text_input(item.get('placeholder'))
                inp.text_size = 0.4
                inp.password = item['type'] == 'password'
                inp.number = item['type'] == 'number'

            elif item['type'] == 'dropdown':
                inp = ln2.add_new_dropdown()
                inp.items = [nanome.ui.DropdownItem(name) for name in item['items']]
                if not inp.items:
                    raise Exception('No items found for dropdown')
                inp.items[0].selected = True

            elif item['type'] == 'toggle':
                inp = ln2.add_new_toggle_switch('')

            elif item['type'] == 'molecule':
                inp = ln2.add_new_dropdown()
                for complex in complexes:
                    ddi = nanome.ui.DropdownItem(complex.name)
                    ddi.index = complex.index
                    inp.items.append(ddi)

            self.inputs.append((item, inp))
            self.lst.items.append(ln)

        self.ln_buttons.enabled = True
        self.update_menu(self.menu)

    @async_callback
    async def continue_request(self, btn):
        if not self.api.requests:
            self.show_endpoints()
            return

        for item, inp in self.inputs:
            if item['type'] in ['number', 'password', 'text']:
                self.api.set_input_value(item, inp.input_text)

            elif item['type'] == 'dropdown':
                ddi = next(i for i in inp.items if i.selected)
                self.api.set_input_value(item, ddi.name)

            elif item['type'] == 'toggle':
                self.api.set_input_value(item, inp.selected)

            elif item['type'] == 'molecule':
                ddi = next(i for i in inp.items if i.selected)
                format = nanome.util.enums.ExportFormats[item['format'].upper()]
                results = await self.request_export(format, entities=[ddi.index])
                self.api.set_input_value(item, results[0])

        self.api.continue_request()

    def render_output(self, outputs):
        self.lst.items.clear()
        self.lst.display_rows = 7

        for output in outputs:
            ln = nanome.ui.LayoutNode()
            ln.set_padding(top=0.01, down=0.01, left=0.02)
            ln.layout_orientation = ln.LayoutTypes.horizontal

            ln1 = ln.create_child_node()
            ln1.set_padding(right=0.01)
            lbl = ln1.add_new_label(output['label'])
            lbl.text_max_size = 0.5
            lbl.text_vertical_align = lbl.VertAlignOptions.Middle

            ln2 = ln.create_child_node()
            ln2.set_padding(left=0.01)
            lbl = ln2.add_new_label(output['value'])
            lbl.text_max_size = 0.5
            lbl.text_horizontal_align = lbl.HorizAlignOptions.Right
            lbl.text_vertical_align = lbl.VertAlignOptions.Middle

            self.lst.items.append(ln)

        self.ln_buttons.enabled = True
        self.update_menu(self.menu)


def main():
    plugin = nanome.Plugin('Requester', 'A Nanome Plugin to make requests to APIs', 'other', False)
    plugin.set_plugin_class(Requester)
    plugin.run()


if __name__ == '__main__':
    main()
