import {BaseChart} from "@/views/chat/component/BaseChart.ts";
import {TableSheet, type S2Options, type S2DataConfig, type S2MountContainer} from "@antv/s2";

export class Table extends BaseChart {

    table?: TableSheet = undefined

    container: S2MountContainer | null = null

    constructor(id: string) {
        super(id, "table");
        this.container = document.getElementById(id);
    }

    init(axis: Array<{ name: string; value: string; type: "x" | "y" }>, data: Array<{ [key: string]: any }>) {
        super.init(axis, data);

        const s2DataConfig: S2DataConfig = {
            fields: {
                columns: this.axis?.map(a => a.value) ?? [],
            },
            meta: this.axis?.map(a => {
                return {
                    field: a.value,
                    name: a.name
                }
            }) ?? [],
            data: this.data,
        };

        const s2Options: S2Options = {
            width: 600,
            height: 480,
            placeholder: {
                cell: '-',
                empty: {
                    icon: 'Empty',
                    description: 'No Data',
                },
            },
        };

        if (this.container) {
            this.table = new TableSheet(this.container, s2DataConfig, s2Options);
        }

    }

    render() {
        this.table?.render()
    }

    destroy() {
        this.table?.destroy()
    }

}