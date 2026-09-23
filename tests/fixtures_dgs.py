"""Texto DGS sintético con la misma topología que fixtures.py (anillo
B1-B2-B3 + ramal B4 + barra B5 fuera de servicio), para probar el parser sin
depender de PowerFactory ni de un archivo real."""

TEXTO_DGS_SINTETICO = """\
$$ElmTerm;ID(a:15);loc_name(a:40);fold_id(p);outserv(i);uknom(r);GPSlat(r);GPSlon(r);cpZone(a:20);cpArea(a:20)
*  Terminales (barras)
  1;Santiago;;0;220;-33.4489;-70.6693;Centro;SIC
  2;Valparaiso;;0;220;-33.0472;-71.6127;Centro;SIC
  3;Rancagua;;0;220;-34.1708;-70.7444;Centro;SIC
  4;Curico;;0;110;-34.9828;-71.2394;Sur;SIC
  5;FueraDeServicio;;1;110;;;Sur;SIC
$$StaCubic;ID(a:15);loc_name(a:40);fold_id(p);obj_id(p)
*  Cubiculos: conectan barras (fold_id) con elementos (obj_id)
  101;Cub1;1;201
  102;Cub2;2;201
  103;Cub3;2;202
  104;Cub4;3;202
  105;Cub5;3;203
  106;Cub6;1;203
  107;Cub7;3;204
  108;Cub8;4;204
  109;Cub9;1;301
  110;Cub10;4;302
  111;Cub11;3;303
$$ElmLne;ID(a:15);loc_name(a:40);typ_id(p);dline(r);outserv(i)
  201;Santiago-Valparaiso;T1;100;0
  202;Valparaiso-Rancagua;T1;130;0
  203;Rancagua-Santiago;T1;90;0
$$TypLne;ID(a:15);loc_name(a:40);rline(r);xline(r);uline(r)
  T1;LineType220;0,01;0,1;220
$$ElmTr2;ID(a:15);loc_name(a:40);typ_id(p);outserv(i)
  204;Rancagua-Curico;TT1;0
$$TypTr2;ID(a:15);loc_name(a:40);uktr(r);utrn_h(r);utrn_l(r);strn(r);pcutr(r)
  TT1;TrafoType;10;100;10;100;100
$$ElmSym;ID(a:15);loc_name(a:40);pgini(r);outserv(i);cpZone(a:20);cpArea(a:20)
  301;Central1;300;0;Centro;SIC
$$ElmLod;ID(a:15);loc_name(a:40);plini(r);outserv(i);cpZone(a:20);cpArea(a:20)
  302;ConsumoCurico;80;0;Sur;SIC
  303;ConsumoRancagua;120;0;Centro;SIC
"""
