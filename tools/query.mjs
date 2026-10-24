// Same pure selector as UI/API. stdin is a snapshot; argv is a JSON filter object.
import {select,geojson} from '../web/query.js';
let text='';for await(const chunk of process.stdin)text+=chunk;
const input=JSON.parse(text),args=input.filters||JSON.parse(process.argv[2]||'{}'),result=select(input.snapshot||input,args.filters||args);
console.log(JSON.stringify(args.geojson?geojson(result):result));
