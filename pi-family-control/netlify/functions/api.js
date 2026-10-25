const crypto = require("node:crypto");
const ITER = 600000;
const DAYS = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"];
const out = (statusCode, body, headers={}) => ({statusCode,headers:{"Content-Type":"application/json; charset=utf-8","Cache-Control":"no-store","X-Content-Type-Options":"nosniff",...headers},body:JSON.stringify(body)});
const bodyOf = e => {try{return JSON.parse(e.body||"{}")}catch{return {}}};
const b64 = s => Buffer.from(s).toString("base64url");
const sign = s => crypto.createHmac("sha256",process.env.SESSION_SECRET||"missing").update(s).digest("base64url");
function session(e) {
  const m=(e.headers.cookie||e.headers.Cookie||"").match(/(?:^|;\\s*)pi_session=([^;]+)/);
  if(!m)return false; const p=m[1].split("."); if(p.length!==2)return false;
  const a=Buffer.from(p[1]),b=Buffer.from(sign(p[0]));
  if(a.length!==b.length||!crypto.timingSafeEqual(a,b))return false;
  try{return JSON.parse(Buffer.from(p[0],"base64url").toString()).exp>Date.now()/1000}catch{return false}
}
function device(e,b) {
 const a=Buffer.from(e.headers["x-device-token"]||b.deviceToken||""), z=Buffer.from(process.env.DEVICE_TOKEN||"");
 return a.length>0&&a.length===z.length&&crypto.timingSafeEqual(a,z);
}
function hash(p,s,i=ITER){return crypto.pbkdf2Sync(p,s,i,32,"sha256").toString("hex")}
function cookie(v,age=604800){return `pi_session=${v}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=${age}`}
async function gist(method,payload) {
 const r=await fetch(`https://api.github.com/gists/${process.env.GIST_ID}`,{method,headers:{"Authorization":`Bearer ${process.env.GITHUB_TOKEN}`,"Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28","Content-Type":"application/json","User-Agent":"pi-family-control"},...(payload?{body:JSON.stringify(payload)}:{})});
 if(!r.ok)throw new Error("GitHub Gist API HTTP "+r.status);return r.json();
}
async function read(){const g=await gist("GET");const f=g.files?.["config.json"];if(!f?.content)throw new Error('Gist needs config.json');return JSON.parse(f.content)}
async function write(c){await gist("PATCH",{files:{"config.json":{content:JSON.stringify(c,null,2)}}})}
function clean(c){const x=JSON.parse(JSON.stringify(c));delete x.auth;return x}
function makeSession(){const p=b64(JSON.stringify({exp:Math.floor(Date.now()/1000)+604800}));return p+"."+sign(p)}
function validPassword(p){return typeof p==="string"&&p.length>=10&&p.length<=200}
exports.handler=async e=>{
 const op=(e.path||"").split("/").filter(Boolean).pop()||"", b=bodyOf(e);
 try{
  if(op==="status"&&e.httpMethod==="GET"){const c=await read();return out(200,{initialized:!!c.initialized})}
  if(op==="setup"&&e.httpMethod==="POST"){
   const c=await read();if(c.initialized)return out(409,{error:"初回設定は完了済みです。ログインしてください。"});
   if(!validPassword(b.password))return out(400,{error:"パスワードは10文字以上にしてください。"});
   const salt=crypto.randomBytes(16).toString("hex");c.auth={salt,passwordHash:hash(b.password,salt),hashIterations:ITER};c.initialized=true;await write(c);
   return out(200,{ok:true},{"Set-Cookie":cookie(makeSession())});
  }
  if(op==="login"&&e.httpMethod==="POST"){
   const c=await read();if(!c.initialized)return out(400,{error:"先に初回設定してください。"});
   const a=Buffer.from(hash(String(b.password||""),c.auth.salt,c.auth.hashIterations||ITER),"hex"),z=Buffer.from(c.auth.passwordHash,"hex");
   if(a.length!==z.length||!crypto.timingSafeEqual(a,z))return out(401,{error:"パスワードが違います。"});
   return out(200,{ok:true},{"Set-Cookie":cookie(makeSession())});
  }
  if(op==="logout"&&e.httpMethod==="POST")return out(200,{ok:true},{"Set-Cookie":cookie("",0)});
  if(op==="device-state"&&e.httpMethod==="GET"){if(!device(e,b))return out(401,{error:"Unauthorized"});return out(200,clean(await read()))}
  if(op==="device-report"&&e.httpMethod==="POST"){
   if(!device(e,b))return out(401,{error:"Unauthorized"});const date=String(b.date||""),secs=Math.max(0,Math.min(120,Math.floor(Number(b.seconds)||0)));
   if(!/^\\d{4}-\\d{2}-\\d{2}$/.test(date))return out(400,{error:"Invalid date"});
   const c=await read();c.usage=c.usage||{daily:{}};c.usage.daily=c.usage.daily||{};const d=c.usage.daily[date]||{seconds:0};d.seconds=(Number(d.seconds)||0)+secs;d.updatedAt=new Date().toISOString();c.usage.daily[date]=d;await write(c);return out(200,{ok:true});
  }
  if(!session(e))return out(401,{error:"ログインしてください。"});
  if(op==="config"&&e.httpMethod==="GET")return out(200,clean(await read()));
  if(op==="config"&&e.httpMethod==="POST"){
   const c=await read(),n=b.config||{};
   if(n.settings){c.settings.scheduleEnabled=!!n.settings.scheduleEnabled;const lim=n.settings.dailyLimitMinutes;c.settings.dailyLimitMinutes=lim===null||lim===""?null:Math.max(1,Math.min(1440,Number(lim)||1));c.settings.extensionMinutes=Math.max(1,Math.min(240,Number(n.settings.extensionMinutes)||15))}
   if(n.schedule)for(const d of DAYS){const x=n.schedule[d];if(!x)continue;const ok=t=>typeof t==="string"&&/^([01]\\d|2[0-3]):[0-5]\\d$/.test(t);if(!ok(x.start)||!ok(x.end))return out(400,{error:"時刻はHH:MMで入力してください"});c.schedule[d]={enabled:!!x.enabled,start:x.start,end:x.end}}
   if(n.control){if(typeof n.control.manualLock==="boolean")c.control.manualLock=n.control.manualLock;if(n.control.extendToday){const today=new Intl.DateTimeFormat("en-CA",{timeZone:"Asia/Tokyo",year:"numeric",month:"2-digit",day:"2-digit"}).format(new Date());const prior=(c.control.extensionDate===today?Number(c.control.todayExtensionMinutes)||0:0);c.control.extensionDate=today;c.control.todayExtensionMinutes=prior+Math.max(1,Math.min(240,Number(n.control.extendMinutes)||c.settings.extensionMinutes))}}
   c.control.updatedAt=new Date().toISOString();await write(c);return out(200,clean(c));
  }
  if(op==="change-password"&&e.httpMethod==="POST"){
   const c=await read();if(!validPassword(b.newPassword))return out(400,{error:"新しいパスワードは10文字以上必要です"});
   const a=Buffer.from(hash(String(b.currentPassword||""),c.auth.salt,c.auth.hashIterations||ITER),"hex"),z=Buffer.from(c.auth.passwordHash,"hex");
   if(a.length!==z.length||!crypto.timingSafeEqual(a,z))return out(401,{error:"現在のパスワードが違います"});
   const salt=crypto.randomBytes(16).toString("hex");c.auth={salt,passwordHash:hash(b.newPassword,salt),hashIterations:ITER};await write(c);return out(200,{ok:true});
  }
  return out(404,{error:"Not found"});
 }catch(err){console.error(err);return out(500,{error:"サーバーエラー。Netlify環境変数、Gist ID、config.jsonを確認してください。"})}
};
