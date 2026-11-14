// Runs the comparability-gate panel tests written by the FLARE lane (flare/flare.test.mjs) inside
// `npm test`, whose glob only covers tests/*.test.mjs. Importing the file registers its tests here;
// the tests themselves stay owned by the FLARE lane and are not copied.
import '../flare/flare.test.mjs';
