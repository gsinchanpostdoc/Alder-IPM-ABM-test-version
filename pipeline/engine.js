// Loads the AlderIPM-Sim web engine (parameters.js, model.js, control.js) unchanged into Node.
const fs = require('fs'), path = require('path'), vm = require('vm');
const JS = path.join(__dirname, '..', 'web', 'js');
const src = ['parameters.js', 'model.js', 'control.js'].map(f => fs.readFileSync(path.join(JS, f), 'utf8')).join('\n');
vm.runInThisContext(src + '\nglobalThis.__alder = { AlderIPMSimModel, getDefaults, PARAM_REGISTRY, ControlComparator };', { filename: 'alder-engine.js' });
module.exports = globalThis.__alder;
