if(!self.define){const e=e=>{"require"!==e&&(e+=".js");let i=Promise.resolve();return s[e]||(i=new Promise((async i=>{if("document"in self){const s=document.createElement("script");s.src=e,document.head.appendChild(s),s.onload=i}else importScripts(e),i()}))),i.then((()=>{if(!s[e])throw new Error(`Module ${e} didn’t register its module`);return s[e]}))},i=(i,s)=>{Promise.all(i.map(e)).then((e=>s(1===e.length?e[0]:e)))},s={require:Promise.resolve(i)};self.define=(i,c,r)=>{s[i]||(s[i]=Promise.resolve().then((()=>{let s={};const d={uri:location.origin+i.slice(1)};return Promise.all(c.map((i=>{switch(i){case"exports":return s;case"module":return d;default:return e(i)}}))).then((e=>{const i=r(...e);return s.default||(s.default=i),s}))})))}}define("./service-worker.js",["./workbox-f7715658"],(function(e){"use strict";self.addEventListener("message",(e=>{e.data&&"SKIP_WAITING"===e.data.type&&self.skipWaiting()})),e.precacheAndRoute([{url:"404.html",revision:"0156999ee0fa5adfcbde3d3b20f3b4ae"},{url:"about/index.html",revision:"5c752fda57df041227131372acbddc49"},{url:"archives/2021/07/index.html",revision:"4d28b877d0775748fef79d3ac80fdc80"},{url:"archives/2021/index.html",revision:"4d28b877d0775748fef79d3ac80fdc80"},{url:"archives/index.html",revision:"4d28b877d0775748fef79d3ac80fdc80"},{url:"baidu_verify_code-oimgUEb2tx.html",revision:"a6611dd8a143fa5e82a2520d8cd2ca8c"},{url:"categories/index.html",revision:"475eeccbc16c578477e33a7c74d19f6c"},{url:"css/gitalk.css",revision:"5ce280d86637a41c57fdc51fd463237a"},{url:"css/indeximg-hover.css",revision:"ed8fc2d2fff11ef21e142142c4053558"},{url:"css/lazyload-ani.css",revision:"bf9e519b6b10cd0b9563c2c1e66bc559"},{url:"css/macpanel.css",revision:"bcef0f801e110223e70ba56f69e31547"},{url:"css/main.css",revision:"d5bc0ec38ad437f5c47529f4e3884936"},{url:"css/scrollbar.css",revision:"d5dcd3372385bc7adb11b54ec15bbf85"},{url:"css/twikoo.css",revision:"a3333ff8b2a7ebb7ae63c3e07c600742"},{url:"customize-some-effects-for-hexofluid/index.html",revision:"f001f1237d29f1220b8fdd368f0ab208"},{url:"img/avatar.png",revision:"2d9aa61e592b26e2745f3c161c48c397"},{url:"img/default.png",revision:"cbecf637ecf1059c2ff594cc419a04f9"},{url:"img/dreams.png",revision:"c5b09f2243da27c47f06498a8f652c91"},{url:"img/favicon.png",revision:"5603316bb5bc54a9d5cab14fddd4c510"},{url:"img/Fluid.png",revision:"859dcbfb6f273b6a6bfe535225b231c3"},{url:"img/Fluid144.png",revision:"ed0f6f8e195520dea26cd95f0529da33"},{url:"img/Fluid2.png",revision:"9b3bb0e70c3954f7791e0b73fc708d2f"},{url:"img/loading.gif",revision:"15657539044e11a19a1c6c7e3073d1b3"},{url:"img/loading2.jpg",revision:"3d0d2a089de0f5544783b43fbdc4d572"},{url:"img/police_beian.png",revision:"b769e8dfde5660239317ed60758dba13"},{url:"img/sunset.jpg",revision:"e45a91a1fe88286b211822e3b9cf0f93"},{url:"img/sunset2.jpg",revision:"34ebf5c50a98db3dfc3cbed990dc5a85"},{url:"img/test.png",revision:"170d4f4b10f327b15e0762dc72ed45f4"},{url:"index.html",revision:"e965d8df185ad5008a268b2535764b9c"},{url:"js/boot.js",revision:"df6699be634b89c020e50370f868f37f"},{url:"js/color-schema.js",revision:"d19f1aa40bdbdca2ffbbea5d6525afe4"},{url:"js/debouncer.js",revision:"b191fcef450414f12dd272f9a75b4576"},{url:"js/events.js",revision:"6c5f9959062cebd85db375e32e736201"},{url:"js/lazyload.js",revision:"cf2320cf7a65c67911b1fae9bb4958f3"},{url:"js/leancloud.js",revision:"eb5eb5f71bdb5d50dbf8082e64bfd0e6"},{url:"js/local-search.js",revision:"53461574609e41159a714670d9b66c0b"},{url:"js/plugins.js",revision:"93fa930e12b7596433529edc1b5458df"},{url:"js/utils.js",revision:"3eb420fea7d1d765cc5152f23a1861a3"},{url:"lib/hint/hint.min.css",revision:"b5f3452bff6af473afc6ec1169990093"},{url:"links/index.html",revision:"3ef9f283223c85c072d52a521dfcbd68"},{url:"tags/index.html",revision:"eed64d705a3c8b94819c821a0b4cff4d"}],{})}));
//# sourceMappingURL=service-worker.js.map
