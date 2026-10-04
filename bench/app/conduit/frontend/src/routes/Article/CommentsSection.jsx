import { useState } from "react";
import CommentEditor from "../../components/CommentEditor";
import CommentList from "../../components/CommentList";
import { bug } from "../../helpers/bugs";

function CommentsSection() {
  const [comment, setComment] = useState({});

  const handleUpdates = (e) => {
    if (bug("comment-not-shown")) return; // [testomation bug]
    setComment(e);
  };

  return (
    <div className="row">
      <div className="col-xs-12 col-md-8 offset-md-2">
        <CommentEditor updateComments={handleUpdates} />
        <CommentList triggerUpdate={comment} updateComments={handleUpdates} />
      </div>
    </div>
  );
}

export default CommentsSection;
