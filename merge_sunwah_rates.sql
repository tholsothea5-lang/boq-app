-- ---------------------------------------------------------------------------
-- SUNWAH Project unit-rate lists (from BOQ Bill-6 (Middle) .. Bill-9 (Edge))
-- Idempotent: each category is appended only if its category id is not already
-- present. Safe to re-run. Run in the Supabase SQL editor (or at the end of a
-- full supabase.sql re-run).
-- ---------------------------------------------------------------------------

-- Material List: new category 'SUNWAH · Bill-6 (Middle)' (sunm_b6m)
update public.ledger
set state = jsonb_set(
  state,
  '{materials}',
  COALESCE(state->'materials', '[]'::jsonb) || '{"children": [{"children": [], "id": "sunm_b6m_1", "name": "Termite treatment", "price": 0, "unit": "m2", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b6m_2", "name": "Compact Mix M-30, t=150mm under footing", "price": 52, "unit": "m2", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b6m_3", "name": "Compact Mix M-30, t=1500mm under Slab", "price": 52, "unit": "m2", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b6m_4", "name": "Lean Concrete -100mm , C-18MPa", "price": 78, "unit": "m3", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b6m_5", "name": "Formwork for Footing, Beam, Column, Stair, Lintel and Slab", "price": 13, "unit": "m2", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b6m_6", "name": "Reinforcement for Footing, Beam, Column, Stair, Lintel and Slab", "price": 1.118, "unit": "Kg", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b6m_7", "name": "Wire", "price": 1.3, "unit": "Kg", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b6m_8", "name": "Concrete C-32Mpa (Cube)", "price": 84.5, "unit": "m3", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b6m_9", "name": "Formwork for Beam, Stair, Lintel and Slab", "price": 13, "unit": "m2", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b6m_10", "name": "Reinforcement for Beam, Stair, Lintel and Slab", "price": 1.118, "unit": "Kg", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b6m_11", "name": "Formwork for Beam, Column, Stair, Lintel and Slab", "price": 13, "unit": "m2", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b6m_12", "name": "Reinforcement for Beam, Column, Stair, Lintel and Slab", "price": 1.118, "unit": "Kg", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b6m_13", "name": "Formwork for Beam, Column, Lintel and Slab", "price": 13, "unit": "m2", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b6m_14", "name": "Reinforcement for Beam, Column, Lintel and Slab", "price": 1.118, "unit": "Kg", "note": "", "photos": [], "quantity": 0}], "id": "sunm_b6m", "name": "SUNWAH · Bill-6 (Middle)", "price": 0, "unit": "", "note": "", "photos": [], "quantity": 0}'::jsonb,
  true
)
where id = 1
  and not exists (
    select 1 from jsonb_array_elements(COALESCE(state->'materials', '[]'::jsonb)) c
    where c->>'id' = 'sunm_b6m'
  );

-- Material List: new category 'SUNWAH · Bill-8 (Middle)' (sunm_b8m)
update public.ledger
set state = jsonb_set(
  state,
  '{materials}',
  COALESCE(state->'materials', '[]'::jsonb) || '{"children": [{"children": [], "id": "sunm_b8m_1", "name": "Brick wall -100mm", "price": 11.57, "unit": "m2", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b8m_2", "name": "Waterproof", "price": 13, "unit": "m2", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b8m_3", "name": "Trees and grass", "price": 195, "unit": "m2", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b8m_4", "name": "Soil", "price": 3.9, "unit": "m3", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b8m_5", "name": "Brick wall -200mm", "price": 14.3, "unit": "m2", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b8m_6", "name": "Plastering (inside & outside)", "price": 6.5, "unit": "m2", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b8m_7", "name": "Painting (inside & outside)", "price": 3.25, "unit": "m2", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b8m_8", "name": "Lintel 100mm", "price": 0, "unit": "m", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b8m_9", "name": "Lintel 200mm", "price": 0, "unit": "m", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b8m_10", "name": "CP-01 white paint on slab soffit", "price": 3.38, "unit": "m2", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b8m_11", "name": "CP-02 Gypsum ceiling with water resistant colour white, semi-glossy, 9mmthk", "price": 10.4, "unit": "m2", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b8m_12", "name": "Floor Tiles for living room, dining room and kitchen", "price": 23.4, "unit": "m2", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b8m_13", "name": "Tiles skirting", "price": 5.85, "unit": "m", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b8m_14", "name": "W.C Floor Tiles + Laundry", "price": 22.1, "unit": "m2", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b8m_15", "name": "W.C Wall Tiles", "price": 22.1, "unit": "m2", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b8m_16", "name": "Exterior wall tall (Stone texture)", "price": 0, "unit": "m2", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b8m_17", "name": "Waterproof W.C + Laundry", "price": 13, "unit": "m2", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b8m_18", "name": "Tiles for stairs (matt 230x1000)", "price": 32.5, "unit": "m2", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b8m_19", "name": "GD-01 Glass door (2900x3000mm)", "price": 698.3925, "unit": "set", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b8m_20", "name": "GD-04 Glass door (2080x2200mm)", "price": 367.3384, "unit": "set", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b8m_21", "name": "MI-01 Aluminum Window with glass (700x1000mm)", "price": 50.2775, "unit": "set", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b8m_22", "name": "DA-02 PVC Door  (800x2200mm)", "price": 117, "unit": "set", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b8m_23", "name": "SD-01a Steel door (1000x2200)", "price": 273, "unit": "set", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b8m_24", "name": "WA-01 Glass window (600x900)", "price": 38.7855, "unit": "set", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b8m_25", "name": "Lower cabinet", "price": 810.81, "unit": "set", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b8m_26", "name": "Upper cabinet", "price": 750.75, "unit": "set", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b8m_27", "name": "Counter top", "price": 50.7, "unit": "m2", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b8m_28", "name": "Handrail for Stair", "price": 93.6, "unit": "m", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b8m_29", "name": "Vanity cabinet and counter top", "price": 195, "unit": "set", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b8m_30", "name": "CP-03 Gypsum ceiling  colour white, semi-glossy, 9mmthk", "price": 7.8, "unit": "m2", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b8m_31", "name": "Floor Tiles for bedroom", "price": 23.4, "unit": "m2", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b8m_32", "name": "W.C Floor Tiles", "price": 22.1, "unit": "m2", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b8m_33", "name": "Waterproof W.C, balcony", "price": 13, "unit": "m2", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b8m_34", "name": "Temper Glass Door(700x1000)", "price": 56.1925, "unit": "m2", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b8m_35", "name": "DA-03 Wood Door (900x2200)", "price": 273, "unit": "set", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b8m_36", "name": "W.C PVC Door (800x2200mm)", "price": 136.5, "unit": "set", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b8m_37", "name": "WA-02 Glass window (1800x1300)", "price": 168.0705, "unit": "set", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b8m_38", "name": "WA-03 Glass window (1200x1300)", "price": 112.047, "unit": "set", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b8m_39", "name": "WA-05 Glass window (4900x2100)", "price": 739.07925, "unit": "set", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b8m_40", "name": "Handrail balcony", "price": 93.6, "unit": "m2", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b8m_41", "name": "Shower screen", "price": 217.62, "unit": "set", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b8m_42", "name": "Waterproof to terrace, sky garden", "price": 13, "unit": "m2", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b8m_43", "name": "Glass skylight roof", "price": 126.75, "unit": "m2", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b8m_44", "name": "Floor Tiles", "price": 23.4, "unit": "m2", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b8m_45", "name": "Room Door SD-02a (900x2200)", "price": 273, "unit": "Pcs", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b8m_46", "name": "Planter box", "price": 78, "unit": "m", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b8m_47", "name": "Concrete louver", "price": 35.1, "unit": "m2", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b8m_48", "name": "Glass block", "price": 50.7, "unit": "m2", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b8m_49", "name": "Waterproofing R.C  Roof", "price": 13, "unit": "m2", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b8m_50", "name": "Stainless steel water Tank", "price": 0, "unit": "Pcs", "note": "", "photos": [], "quantity": 0}], "id": "sunm_b8m", "name": "SUNWAH · Bill-8 (Middle)", "price": 0, "unit": "", "note": "", "photos": [], "quantity": 0}'::jsonb,
  true
)
where id = 1
  and not exists (
    select 1 from jsonb_array_elements(COALESCE(state->'materials', '[]'::jsonb)) c
    where c->>'id' = 'sunm_b8m'
  );

-- Material List: new category 'SUNWAH · Bill-8 (Edge)' (sunm_b8e)
update public.ledger
set state = jsonb_set(
  state,
  '{materials}',
  COALESCE(state->'materials', '[]'::jsonb) || '{"children": [{"children": [], "id": "sunm_b8e_1", "name": "GD-02 Glass door (4100x3000mm)", "price": 987.3825, "unit": "set", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b8e_2", "name": "GD-03 Glass door (3000x2200mm)", "price": 529.815, "unit": "set", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b8e_3", "name": "WA-06 Glass window (2900x2100)", "price": 437.41425, "unit": "set", "note": "", "photos": [], "quantity": 0}], "id": "sunm_b8e", "name": "SUNWAH · Bill-8 (Edge)", "price": 0, "unit": "", "note": "", "photos": [], "quantity": 0}'::jsonb,
  true
)
where id = 1
  and not exists (
    select 1 from jsonb_array_elements(COALESCE(state->'materials', '[]'::jsonb)) c
    where c->>'id' = 'sunm_b8e'
  );

-- Material List: new category 'SUNWAH · Bill-9 (Middle)' (sunm_b9m)
update public.ledger
set state = jsonb_set(
  state,
  '{materials}',
  COALESCE(state->'materials', '[]'::jsonb) || '{"children": [{"children": [], "id": "sunm_b9m_1", "name": "Waterproof W.C", "price": 13, "unit": "m2", "note": "", "photos": [], "quantity": 0}, {"children": [], "id": "sunm_b9m_2", "name": "DA-01a Wood Door  (800x2200mm)", "price": 273, "unit": "set", "note": "", "photos": [], "quantity": 0}], "id": "sunm_b9m", "name": "SUNWAH · Bill-9 (Middle)", "price": 0, "unit": "", "note": "", "photos": [], "quantity": 0}'::jsonb,
  true
)
where id = 1
  and not exists (
    select 1 from jsonb_array_elements(COALESCE(state->'materials', '[]'::jsonb)) c
    where c->>'id' = 'sunm_b9m'
  );

-- Material List: new category 'SUNWAH · Bill-9 (Edge)' (sunm_b9e)
update public.ledger
set state = jsonb_set(
  state,
  '{materials}',
  COALESCE(state->'materials', '[]'::jsonb) || '{"children": [{"children": [], "id": "sunm_b9e_1", "name": "Exterior wall tiles (Stone texture)", "price": 0, "unit": "m2", "note": "", "photos": [], "quantity": 0}], "id": "sunm_b9e", "name": "SUNWAH · Bill-9 (Edge)", "price": 0, "unit": "", "note": "", "photos": [], "quantity": 0}'::jsonb,
  true
)
where id = 1
  and not exists (
    select 1 from jsonb_array_elements(COALESCE(state->'materials', '[]'::jsonb)) c
    where c->>'id' = 'sunm_b9e'
  );

-- Labor List: new category 'SUNWAH · Bill-6 (Middle)' (sunl_b6m)
update public.ledger
set state = jsonb_set(
  state,
  '{labor}',
  COALESCE(state->'labor', '[]'::jsonb) || '{"children": [{"children": [], "id": "sunl_b6m_1", "name": "Soil Excavation", "price": 3.9, "unit": "m3"}, {"children": [], "id": "sunl_b6m_2", "name": "Breaking head of Pilling", "price": 10.4, "unit": "Pcs"}, {"children": [], "id": "sunl_b6m_3", "name": "Soil back fill", "price": 3.9, "unit": "m3"}, {"children": [], "id": "sunl_b6m_4", "name": "Termite treatment", "price": 0, "unit": "m2"}, {"children": [], "id": "sunl_b6m_5", "name": "Compact Mix M-30, t=150mm under footing", "price": 3.9, "unit": "m2"}, {"children": [], "id": "sunl_b6m_6", "name": "Compact Mix M-30, t=1500mm under Slab", "price": 3.9, "unit": "m2"}, {"children": [], "id": "sunl_b6m_7", "name": "Lean Concrete -100mm , C-18MPa", "price": 6.5, "unit": "m3"}, {"children": [], "id": "sunl_b6m_8", "name": "Formwork for Footing, Beam, Column, Stair, Lintel and Slab", "price": 6.5, "unit": "m2"}, {"children": [], "id": "sunl_b6m_9", "name": "Reinforcement for Footing, Beam, Column, Stair, Lintel and Slab", "price": 0.195, "unit": "Kg"}, {"children": [], "id": "sunl_b6m_10", "name": "Wire", "price": 0, "unit": "Kg"}, {"children": [], "id": "sunl_b6m_11", "name": "Concrete C-32Mpa (Cube)", "price": 13, "unit": "m3"}, {"children": [], "id": "sunl_b6m_12", "name": "Formwork for Beam, Stair, Lintel and Slab", "price": 6.5, "unit": "m2"}, {"children": [], "id": "sunl_b6m_13", "name": "Reinforcement for Beam, Stair, Lintel and Slab", "price": 0.195, "unit": "Kg"}, {"children": [], "id": "sunl_b6m_14", "name": "Formwork for Beam, Column, Stair, Lintel and Slab", "price": 6.5, "unit": "m2"}, {"children": [], "id": "sunl_b6m_15", "name": "Reinforcement for Beam, Column, Stair, Lintel and Slab", "price": 0.195, "unit": "Kg"}, {"children": [], "id": "sunl_b6m_16", "name": "Formwork for Beam, Column, Lintel and Slab", "price": 6.5, "unit": "m2"}, {"children": [], "id": "sunl_b6m_17", "name": "Reinforcement for Beam, Column, Lintel and Slab", "price": 0.195, "unit": "Kg"}], "id": "sunl_b6m", "name": "SUNWAH · Bill-6 (Middle)", "price": 0, "unit": ""}'::jsonb,
  true
)
where id = 1
  and not exists (
    select 1 from jsonb_array_elements(COALESCE(state->'labor', '[]'::jsonb)) c
    where c->>'id' = 'sunl_b6m'
  );

-- Labor List: new category 'SUNWAH · Bill-8 (Middle)' (sunl_b8m)
update public.ledger
set state = jsonb_set(
  state,
  '{labor}',
  COALESCE(state->'labor', '[]'::jsonb) || '{"children": [{"children": [], "id": "sunl_b8m_1", "name": "Brick wall -100mm", "price": 10.4, "unit": "m2"}, {"children": [], "id": "sunl_b8m_2", "name": "Waterproof", "price": 6.5, "unit": "m2"}, {"children": [], "id": "sunl_b8m_3", "name": "Trees and grass", "price": 39, "unit": "m2"}, {"children": [], "id": "sunl_b8m_4", "name": "Soil", "price": 3.9, "unit": "m3"}, {"children": [], "id": "sunl_b8m_5", "name": "Brick wall -200mm", "price": 9.1, "unit": "m2"}, {"children": [], "id": "sunl_b8m_6", "name": "Plastering (inside & outside)", "price": 5.85, "unit": "m2"}, {"children": [], "id": "sunl_b8m_7", "name": "Painting (inside & outside)", "price": 3.25, "unit": "m2"}, {"children": [], "id": "sunl_b8m_8", "name": "Lintel 100mm", "price": 0, "unit": "m"}, {"children": [], "id": "sunl_b8m_9", "name": "Lintel 200mm", "price": 0, "unit": "m"}, {"children": [], "id": "sunl_b8m_10", "name": "CP-01 white paint on slab soffit", "price": 3.25, "unit": "m2"}, {"children": [], "id": "sunl_b8m_11", "name": "CP-02 Gypsum ceiling with water resistant colour white, semi-glossy, 9mmthk", "price": 5.2, "unit": "m2"}, {"children": [], "id": "sunl_b8m_12", "name": "Floor Tiles for living room, dining room and kitchen", "price": 6.5, "unit": "m2"}, {"children": [], "id": "sunl_b8m_13", "name": "Tiles skirting", "price": 2.6, "unit": "m"}, {"children": [], "id": "sunl_b8m_14", "name": "W.C Floor Tiles + Laundry", "price": 8.45, "unit": "m2"}, {"children": [], "id": "sunl_b8m_15", "name": "W.C Wall Tiles", "price": 8.45, "unit": "m2"}, {"children": [], "id": "sunl_b8m_16", "name": "Exterior wall tall (Stone texture)", "price": 0, "unit": "m2"}, {"children": [], "id": "sunl_b8m_17", "name": "Waterproof W.C + Laundry", "price": 6.5, "unit": "m2"}, {"children": [], "id": "sunl_b8m_18", "name": "Tiles for stairs (matt 230x1000)", "price": 23.4, "unit": "m2"}, {"children": [], "id": "sunl_b8m_19", "name": "GD-01 Glass door (2900x3000mm)", "price": 376.0575, "unit": "set"}, {"children": [], "id": "sunl_b8m_20", "name": "GD-04 Glass door (2080x2200mm)", "price": 197.7976, "unit": "set"}, {"children": [], "id": "sunl_b8m_21", "name": "MI-01 Aluminum Window with glass (700x1000mm)", "price": 27.0725, "unit": "set"}, {"children": [], "id": "sunl_b8m_22", "name": "DA-02 PVC Door  (800x2200mm)", "price": 78, "unit": "set"}, {"children": [], "id": "sunl_b8m_23", "name": "SD-01a Steel door (1000x2200)", "price": 182, "unit": "set"}, {"children": [], "id": "sunl_b8m_24", "name": "WA-01 Glass window (600x900)", "price": 20.8845, "unit": "set"}, {"children": [], "id": "sunl_b8m_25", "name": "Lower cabinet", "price": 540.54, "unit": "set"}, {"children": [], "id": "sunl_b8m_26", "name": "Upper cabinet", "price": 500.5, "unit": "set"}, {"children": [], "id": "sunl_b8m_27", "name": "Counter top", "price": 33.8, "unit": "m2"}, {"children": [], "id": "sunl_b8m_28", "name": "Handrail for Stair", "price": 62.4, "unit": "m"}, {"children": [], "id": "sunl_b8m_29", "name": "Vanity cabinet and counter top", "price": 130, "unit": "set"}, {"children": [], "id": "sunl_b8m_30", "name": "CP-03 Gypsum ceiling  colour white, semi-glossy, 9mmthk", "price": 3.9, "unit": "m2"}, {"children": [], "id": "sunl_b8m_31", "name": "Floor Tiles for bedroom", "price": 6.5, "unit": "m2"}, {"children": [], "id": "sunl_b8m_32", "name": "W.C Floor Tiles", "price": 8.45, "unit": "m2"}, {"children": [], "id": "sunl_b8m_33", "name": "Waterproof W.C, balcony", "price": 6.5, "unit": "m2"}, {"children": [], "id": "sunl_b8m_34", "name": "Temper Glass Door(700x1000)", "price": 30.2575, "unit": "m2"}, {"children": [], "id": "sunl_b8m_35", "name": "DA-03 Wood Door (900x2200)", "price": 182, "unit": "set"}, {"children": [], "id": "sunl_b8m_36", "name": "W.C PVC Door (800x2200mm)", "price": 58.5, "unit": "set"}, {"children": [], "id": "sunl_b8m_37", "name": "WA-02 Glass window (1800x1300)", "price": 90.4995, "unit": "set"}, {"children": [], "id": "sunl_b8m_38", "name": "WA-03 Glass window (1200x1300)", "price": 60.333, "unit": "set"}, {"children": [], "id": "sunl_b8m_39", "name": "WA-05 Glass window (4900x2100)", "price": 397.96575, "unit": "set"}, {"children": [], "id": "sunl_b8m_40", "name": "Handrail balcony", "price": 62.4, "unit": "m2"}, {"children": [], "id": "sunl_b8m_41", "name": "Shower screen", "price": 145.08, "unit": "set"}, {"children": [], "id": "sunl_b8m_42", "name": "Waterproof to terrace, sky garden", "price": 6.5, "unit": "m2"}, {"children": [], "id": "sunl_b8m_43", "name": "Glass skylight roof", "price": 68.25, "unit": "m2"}, {"children": [], "id": "sunl_b8m_44", "name": "Floor Tiles", "price": 6.5, "unit": "m2"}, {"children": [], "id": "sunl_b8m_45", "name": "Room Door SD-02a (900x2200)", "price": 182, "unit": "Pcs"}, {"children": [], "id": "sunl_b8m_46", "name": "Planter box", "price": 52, "unit": "m"}, {"children": [], "id": "sunl_b8m_47", "name": "Concrete louver", "price": 23.4, "unit": "m2"}, {"children": [], "id": "sunl_b8m_48", "name": "Glass block", "price": 50.7, "unit": "m2"}, {"children": [], "id": "sunl_b8m_49", "name": "Waterproofing R.C  Roof", "price": 6.5, "unit": "m2"}, {"children": [], "id": "sunl_b8m_50", "name": "Stainless steel water Tank", "price": 0, "unit": "Pcs"}], "id": "sunl_b8m", "name": "SUNWAH · Bill-8 (Middle)", "price": 0, "unit": ""}'::jsonb,
  true
)
where id = 1
  and not exists (
    select 1 from jsonb_array_elements(COALESCE(state->'labor', '[]'::jsonb)) c
    where c->>'id' = 'sunl_b8m'
  );

-- Labor List: new category 'SUNWAH · Bill-8 (Edge)' (sunl_b8e)
update public.ledger
set state = jsonb_set(
  state,
  '{labor}',
  COALESCE(state->'labor', '[]'::jsonb) || '{"children": [{"children": [], "id": "sunl_b8e_1", "name": "GD-02 Glass door (4100x3000mm)", "price": 531.6675, "unit": "set"}, {"children": [], "id": "sunl_b8e_2", "name": "GD-03 Glass door (3000x2200mm)", "price": 285.285, "unit": "set"}, {"children": [], "id": "sunl_b8e_3", "name": "WA-06 Glass window (2900x2100)", "price": 235.53075, "unit": "set"}], "id": "sunl_b8e", "name": "SUNWAH · Bill-8 (Edge)", "price": 0, "unit": ""}'::jsonb,
  true
)
where id = 1
  and not exists (
    select 1 from jsonb_array_elements(COALESCE(state->'labor', '[]'::jsonb)) c
    where c->>'id' = 'sunl_b8e'
  );

-- Labor List: new category 'SUNWAH · Bill-9 (Middle)' (sunl_b9m)
update public.ledger
set state = jsonb_set(
  state,
  '{labor}',
  COALESCE(state->'labor', '[]'::jsonb) || '{"children": [{"children": [], "id": "sunl_b9m_1", "name": "Waterproof W.C", "price": 6.5, "unit": "m2"}, {"children": [], "id": "sunl_b9m_2", "name": "DA-01a Wood Door  (800x2200mm)", "price": 182, "unit": "set"}], "id": "sunl_b9m", "name": "SUNWAH · Bill-9 (Middle)", "price": 0, "unit": ""}'::jsonb,
  true
)
where id = 1
  and not exists (
    select 1 from jsonb_array_elements(COALESCE(state->'labor', '[]'::jsonb)) c
    where c->>'id' = 'sunl_b9m'
  );

-- Labor List: new category 'SUNWAH · Bill-9 (Edge)' (sunl_b9e)
update public.ledger
set state = jsonb_set(
  state,
  '{labor}',
  COALESCE(state->'labor', '[]'::jsonb) || '{"children": [{"children": [], "id": "sunl_b9e_1", "name": "Exterior wall tiles (Stone texture)", "price": 0, "unit": "m2"}], "id": "sunl_b9e", "name": "SUNWAH · Bill-9 (Edge)", "price": 0, "unit": ""}'::jsonb,
  true
)
where id = 1
  and not exists (
    select 1 from jsonb_array_elements(COALESCE(state->'labor', '[]'::jsonb)) c
    where c->>'id' = 'sunl_b9e'
  );
