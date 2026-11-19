<?php
// Dump PHP tokens of a file as JSON: [[name,text],...]; single char tokens as [char,char]
$out=[];
foreach(token_get_all(file_get_contents($argv[1])) as $t){
  if(is_array($t)) $out[]=[token_name($t[0]),$t[1]]; else $out[]=[$t,$t];
}
echo json_encode($out, JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES);
