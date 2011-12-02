$(function() {
  $(".datepicker").datepicker();
  $('.datepicker, #roomlist input, #start_time_hour, #start_time_minute, #start_time_ampm, #end_time_hour, #end_time_minute, #end_time_ampm').blur(checkDup);
});
  
function checkDup() {
  $.post("/check_conflict", function(responseText){ if(responseText=="yes") $("#message").html("Sorry, another event is already using the room(s) at the time you requested"); });
}
