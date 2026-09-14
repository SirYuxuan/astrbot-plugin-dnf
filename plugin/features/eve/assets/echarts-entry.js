// Source entry for the minimized ECharts runtime used by chart.py.
// Build with: esbuild echarts-entry.js --bundle --minify --format=iife
//             --target=chrome90 --outfile=echarts.min.js
import * as echarts from "echarts/core";
import { LineChart } from "echarts/charts";
import { GridComponent, LegendComponent } from "echarts/components";
import { SVGRenderer } from "echarts/renderers";

echarts.use([LineChart, GridComponent, LegendComponent, SVGRenderer]);
globalThis.echarts = echarts;
