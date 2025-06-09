export abstract class BaseChart {
    id: string;
    _name: string = 'base-chart';
    axis: Array<{ name: string, value: string, type?: 'x' | 'y' }> = [];
    data: Array<{ [key: string]: any }> = [];

    constructor(id: string, name: string) {
        this.id = id;
        this._name = name;
    }

    init(axis: Array<{ name: string, value: string, type?: 'x' | 'y' }>, data: Array<{ [key: string]: any }>): void {
        this.axis = axis;
        this.data = data;
    }

    abstract render(): void

    abstract destroy(): void


}