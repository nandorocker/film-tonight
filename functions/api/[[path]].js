import {handle} from '../../cloud/service.js';
export const onRequest=({request,env})=>handle(request,env);
