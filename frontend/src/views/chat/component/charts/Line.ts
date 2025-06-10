import {BaseG2Chart} from "@/views/chat/component/BaseG2Chart.ts";

export class Line extends BaseG2Chart {

    constructor(id: string) {
        super(id, "line");
    }

    init(axis: Array<{ name: string; value: string; type: "x" | "y" }>, data: Array<{ [key: string]: any }>) {
        super.init(axis, data);

        const x = this.axis.filter(item => item.type === "x");
        const y = this.axis.filter(item => item.type === "y");

        if (x.length == 0 || y.length == 0) {
            return;
        }

        this.chart?.data(data)
            .encode('x', x[0].value)
            .encode('y', y[0].value)
            .scale('x', {
                nice: true,
            })
            .scale('y', {
                nice: true,
            });

        this.chart?.line().label({
            text: 'value',
            style: {
                dx: -10,
                dy: -12,
            },
        });

        this.chart?.point()
            .style('fill', 'white')
            .tooltip(false);

    }

}