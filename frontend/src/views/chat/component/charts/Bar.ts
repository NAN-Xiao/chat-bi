import {BaseG2Chart} from "@/views/chat/component/BaseG2Chart.ts";

export class Bar extends BaseG2Chart {

    constructor(id: string) {
        super(id, "bar");
    }

    init(axis: Array<{ name: string; value: string; type: "x" | "y" }>, data: Array<{ name: string; value: string }>) {
        super.init(axis, data);
        const x = this.axis.filter(item => item.type === "x");
        const y = this.axis.filter(item => item.type === "y");

        if (x.length == 0 || y.length == 0) {
            return;
        }

        this.chart?.interval()
            .coordinate({transform: [{type: 'transpose'}]})
            .data(data)
            .encode('x', x[0].value)
            .encode('y', y[0].value)
            .scale('x', {
                nice: true,
            })
            .scale('y', {
                nice: true,
            })
            .interaction('elementHighlight', { background: true });

    }

}