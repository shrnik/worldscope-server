/* Bootstrap module: collects the ES-module pieces and hands them to the
   classic-script page code as window.CalibExt. Module scripts are deferred,
   so this runs after the page scripts — page code must only touch CalibExt
   inside event handlers, never at top level. */
import * as gradio from './api/gradio.js';
import * as geocalib from './api/geocalib.js';
import * as sam3 from './api/sam3.js';
import * as overpass from './api/overpass.js';
import * as wikipedia from './api/wikipedia.js';
import * as vlm from './api/vlm.js';

window.CalibExt = { gradio, geocalib, sam3, overpass, wikipedia, vlm };
window.dispatchEvent(new Event('calib-ext-ready'));
