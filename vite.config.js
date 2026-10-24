import {defineConfig} from 'vite';
import {resolve} from 'node:path';
export default defineConfig({root:'dist',server:{host:'127.0.0.1',port:5175,strictPort:true,
  fs:{allow:[resolve('dist')],deny:['.env*','.dev.vars','**/.git/**']},
  proxy:{'/api/':{target:'http://127.0.0.1:8788',changeOrigin:true}}}});
