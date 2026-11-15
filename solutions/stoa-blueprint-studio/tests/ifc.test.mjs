import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { decodeStepString, parseArgs, readIfc } from '../src/ifc.mjs';
import { answerIfc, ifcSiblingOf } from '../src/ifc-qa.mjs';

test('STEP strings and argument lists decode', () => {
  assert.equal(decodeStepString('ELUTUBA+K\\X2\\00D600D6\\X0\\K'), 'ELUTUBA+KÖÖK');
  assert.equal(decodeStepString("Peter''s"), "Peter's");
  assert.deepEqual(parseArgs("'a',$,(#1,#2),.T.,IFCLABEL('x'),-1.5E2"), ['a', null, [{ ref: 1 }, { ref: 2 }], true, 'x', -150]);
});

// Tiny synthetic IFC2X3 model in millimetres: one storey, two spaces (one with a stored
// NetFloorArea, one only with an extruded 5 m x 4 m profile), two doors, one wall with base quantities.
const STEP = `ISO-10303-21;
HEADER;FILE_SCHEMA(('IFC2X3'));ENDSEC;
DATA;
#1= IFCSIUNIT(*,.LENGTHUNIT.,.MILLI.,.METRE.);
#2= IFCSIUNIT(*,.AREAUNIT.,$,.SQUARE_METRE.);
#3= IFCUNITASSIGNMENT((#1,#2));
#10= IFCBUILDINGSTOREY('s1',$,'1.korrus',$,$,$,$,$,.ELEMENT.,0.);
#20= IFCSPACE('sp1',$,'101',$,$,$,$,'KORIDOR',.ELEMENT.,.INTERNAL.,$);
#21= IFCSPACE('sp2',$,'102',$,$,$,#30,'MAGAMISTUBA',.ELEMENT.,.INTERNAL.,$);
#30= IFCPRODUCTDEFINITIONSHAPE($,$,(#31));
#31= IFCSHAPEREPRESENTATION($,'Body','SweptSolid',(#32));
#32= IFCEXTRUDEDAREASOLID(#33,$,$,2700.);
#33= IFCARBITRARYCLOSEDPROFILEDEF(.AREA.,$,#34);
#34= IFCPOLYLINE((#35,#36,#37,#38,#35));
#35= IFCCARTESIANPOINT((0.,0.));
#36= IFCCARTESIANPOINT((5000.,0.));
#37= IFCCARTESIANPOINT((5000.,4000.));
#38= IFCCARTESIANPOINT((0.,4000.));
#40= IFCRELAGGREGATES('a1',$,$,$,#10,(#20,#21));
#50= IFCDOOR('d1',$,'D',$,$,$,$,$,2100.,900.);
#51= IFCDOOR('d2',$,'D',$,$,$,$,$,2100.,900.);
#52= IFCWALLSTANDARDCASE('w1',$,'W',$,$,$,$,$);
#53= IFCRELCONTAINEDINSPATIALSTRUCTURE('c1',$,$,$,(#50,#51,#52),#10);
#60= IFCQUANTITYAREA('NetFloorArea',$,$,12.5);
#61= IFCELEMENTQUANTITY('q1',$,'BaseQuantities',$,$,(#60));
#62= IFCRELDEFINESBYPROPERTIES('r1',$,$,$,(#20),#61);
#70= IFCQUANTITYLENGTH('Length',$,$,4500.);
#71= IFCELEMENTQUANTITY('q2',$,'BaseQuantities',$,$,(#70));
#72= IFCRELDEFINESBYPROPERTIES('r2',$,$,$,(#52),#71);
ENDSEC;
END-ISO-10303-21;
`;

test('IFC questions: counts per storey, stored and measured areas, unit conversion', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'stoa-ifc-'));
  await writeFile(join(dir, 'm.ifc'), STEP);
  const m = await readIfc(join(dir, 'm.ifc'));
  const ask = q => answerIfc(m, q);
  assert.equal(ask("How many doors are shown on the floor plan of '1.korrus'?").answer, '2');
  assert.equal(ask('Mitu ruumi on näidatud korruse „1.korrus“ plaanil?').answer, '2');
  assert.equal(ask("What is the net floor area of the room 'KORIDOR (101)' on '1.korrus', in m²?").answer, '12.5 m²');
  assert.equal(ask('Kui suur on ruumi „MAGAMISTUBA (102)“ netopõrandapind korrusel „1.korrus“ (m²)?').answer, '20 m²');
  assert.equal(ask("What is the total net floor area of all rooms (spaces) on '1.korrus', in m²?").answer, '32.5 m²');
  assert.equal(ask("What is the total length of all walls on '1.korrus', in metres?").answer, '4.5 m');
  assert.equal(ask("How many doors are there in the model 'Demo'?").answer, '2');
  assert.equal(ask("What is the net floor area of the room 'SAUN (999)' on '1.korrus', in m²?").status, 'abstained');
});

test('floor-plan PDFs map to their source model', () => {
  assert.equal(ifcSiblingOf('data/ifc_models/bsc-molio_molio-with-uris_plan-02-klder.pdf'), 'data/ifc_models/bsc-molio_molio-with-uris.ifc');
});
